import hashlib
import json
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import geopandas as gpd
import matplotlib as mpl
import matplotlib.gridspec as grid_spec
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredText
from matplotlib.patches import Patch
from scipy.stats import pearsonr, spearmanr
from shapely.geometry import MultiPoint, Point


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DERIVED_DIR = DATA_DIR / "derived"
OUTPUT_DIR = PROJECT_ROOT / "output"
FIGURES_DIR = OUTPUT_DIR / "figures"
TABLES_DIR = OUTPUT_DIR / "tables"

mpl.rcParams["font.family"] = "Helvetica"

RAW_DATA_SOURCES = [
    {
        "path": "data/raw/census/2019_disability.xlsx",
        "sha256": "b3b1c8e36d80d7082bc3ef90cf90f6c193a1c97b726f4be64bb252029617dad8",
        "size": 51506,
        "source": "https://api.beta.ons.gov.uk/v1/filter-outputs/23eb5da8-fef7-402e-b42b-91b9991d6dd4",
        "download": "ons_filter_output:23eb5da8-fef7-402e-b42b-91b9991d6dd4:xls",
        "note": "ONS Census 2021 custom filter output.",
    },
    {
        "path": "data/raw/census/2019_health.csv",
        "sha256": "7fd3266324b3b5cf5cd23700d8eddea94a0b26d058b769cb28fdcb8a2fd2ec43",
        "size": 81292,
        "source": "https://api.beta.ons.gov.uk/v1/datasets/RM014/editions/2021/versions/1",
        "download": "ons_custom_filter:RM014:2021:1:wpc:health_in_general_3a:csv",
        "note": "ONS Census 2021 custom filter generated for Westminster constituencies and General health (3 categories).",
    },
    {
        "path": "data/raw/census/2019_unpaid_care.xlsx",
        "sha256": "c82d55a80f3ed70cccd0042d259e4db810a4478af631e5d15e5882191bf0add9",
        "size": 74546,
        "source": "https://api.beta.ons.gov.uk/v1/filter-outputs/11f0ca17-90e4-4dd7-8812-0f1cf8cc353a",
        "download": "ons_filter_output:11f0ca17-90e4-4dd7-8812-0f1cf8cc353a:xls",
        "note": "ONS Census 2021 custom filter output.",
    },
    {
        "path": "data/raw/census/2024_disability.xlsx",
        "sha256": "736195c3d67b9b0318e8a343a08b6e18decf650555721a727ba06da49672488d",
        "size": 52344,
        "source": "https://api.beta.ons.gov.uk/v1/filter-outputs/e816c41e-5232-490e-8e5a-b569acf85785",
        "download": "ons_filter_output:e816c41e-5232-490e-8e5a-b569acf85785:xls",
        "note": "ONS Census 2021 custom post-2019 constituency output.",
    },
    {
        "path": "data/raw/census/2024_health.csv",
        "sha256": "c187f9a8275d646a7171e2fec44daa8027a584aefe25786d1781bf3d9fc06235",
        "size": 84962,
        "source": "https://api.beta.ons.gov.uk/v1/datasets/RM014/editions/2021/versions/1",
        "download": "ons_custom_filter:RM014:2021:1:p19wpc:health_in_general_3a:csv",
        "note": "ONS Census 2021 custom filter generated for post-2019 Westminster constituencies and General health (3 categories).",
    },
    {
        "path": "data/raw/census/2024_unpaid_care.xlsx",
        "sha256": "97c50be022d94ba747c0fa449a63075a48cfd9891b9465bd71a59864bcec455d",
        "size": 75418,
        "source": "https://api.beta.ons.gov.uk/v1/filter-outputs/f3222b3c-7f45-43dd-a468-aa3c31aea85e",
        "download": "ons_filter_output:f3222b3c-7f45-43dd-a468-aa3c31aea85e:xls",
        "note": "ONS Census 2021 custom post-2019 constituency output.",
    },
    {
        "path": "data/raw/deprivation/File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv",
        "sha256": "0c378543ffd85029ebb9672a9745dbcbde77bcc84a68e2474c8a222df20eee57",
        "size": 9695427,
        "source": "https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019",
        "download": "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/845345/File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv",
        "normalize_newlines": True,
        "note": "Downloaded CSV is normalized to LF line endings before checksum verification.",
    },
    {
        "path": "data/raw/deprivation/deprivation_2025.xlsx",
        "sha256": "da152cbb4f976f71ea2da80e9dc8c8423cd4a4ea7a19b79db7461784175e8b03",
        "size": 779722,
        "source": "https://commonslibrary.parliament.uk/research-briefings/cbp-7327/",
        "download": "https://researchbriefings.files.parliament.uk/documents/CBP-7327/Deprivation-in-English-constituencies.xlsx",
        "note": "House of Commons Library constituency deprivation workbook.",
    },
    {
        "path": "data/raw/deprivation/oa11_lsoa11_lookup.csv",
        "sha256": "f58f69c8e693c617d26da5b0c01a711d9810c4a4b8ae3a817c1f049957a2ef61",
        "size": 3628176,
        "source": "https://geoportal.statistics.gov.uk/",
        "download": "arcgis:oa11_lsoa11_lookup",
        "note": "ONS ArcGIS OA11-to-LSOA11 lookup cached as CSV.",
    },
    {
        "path": "data/raw/deprivation/oa11_pcon11_lookup.csv",
        "sha256": "59e21ed574b0e8b5b3d567bab1785ff4c861ffb786da88066f93a29d262276e0",
        "size": 6512932,
        "source": "https://geoportal.statistics.gov.uk/",
        "download": "arcgis:oa11_pcon11_lookup",
        "note": "ONS ArcGIS OA11-to-PCON11 lookup cached as CSV.",
    },
    {
        "path": "data/raw/life_expectancy/HID_data_Life expectancy and mortality.csv",
        "sha256": "5b7eeda2808cb354386a112ccfc7274a877ce669590b4ee240c39ca803b07bdc",
        "size": 5618322,
        "source": "https://fingertips.phe.org.uk/profile/health-profiles",
        "download": None,
        "note": "OHID Fingertips extract used for the temporal context figure.",
    },
    {
        "path": "data/raw/life_expectancy/trends_in_sii.xlsx",
        "sha256": "8c9ad8da8b868579e3119b147cbfc47b4abcf6e84878aaa65b9c0200f5df8770",
        "size": 10711,
        "source": "https://fingertips.phe.org.uk/profile/health-profiles",
        "download": None,
        "note": "Local workbook of SII trend data used for the temporal context figure.",
    },
    {
        "path": "data/raw/mortality/pcondeathspopulations20192024.xlsx",
        "sha256": "f706b80f2144be283f31cee5eaaf4cdfe9dd49d5d10dacc32e4bfcbe8125cd39",
        "size": 222513,
        "source": "https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/deaths/adhocs/3175numbersandagestandardisedmortalityratesofdeathspopulationcountsbysexandparliamentaryconstituencyenglandandwalesdeathsregisteredin2019and2024",
        "download": "https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/birthsdeathsandmarriages/deaths/adhocs/3175numbersandagestandardisedmortalityratesofdeathspopulationcountsbysexandparliamentaryconstituencyenglandandwalesdeathsregisteredin2019and2024/pcondeathspopulations20192024.xlsx",
        "note": "ONS ad hoc release 3175.",
    },
    {
        "path": "data/raw/voting/HoC-GE2019-results-by-constituency.xlsx",
        "sha256": "18a183e5dbf243c898ebcaed2df7d5b86fe18f2d7fb0ba9af203e26e3a76e36a",
        "size": 164288,
        "source": "https://commonslibrary.parliament.uk/research-briefings/cbp-8749/",
        "download": "https://researchbriefings.files.parliament.uk/documents/CBP-8749/HoC-GE2019-results-by-constituency.xlsx",
        "note": "House of Commons Library detailed constituency results.",
    },
    {
        "path": "data/raw/voting/HoC-GE2024-results-by-constituency.xlsx",
        "sha256": "41c220a08c662f60750477e60c672149ad0b126bf3d7cedddea1b8f1748c05bc",
        "size": 155348,
        "source": "https://commonslibrary.parliament.uk/research-briefings/cbp-10009/",
        "download": "https://researchbriefings.files.parliament.uk/documents/CBP-10009/HoC-GE2024-results-by-constituency.xlsx",
        "note": "House of Commons Library detailed constituency results.",
    },
    {
        "path": "data/shapefile/2019/WPC_Dec_2019_GCB_UK.shp",
        "sha256": "ae65b1d2eae1964f0f9515737e68225a414bfc71ce14d7c568e547bb2e0e5a20",
        "size": 9189180,
        "source": "https://geoportal.statistics.gov.uk/datasets/ons::wpc-dec-2019-generalised-clipped-boundaries-uk",
        "download": None,
        "note": "ONS 2019 Westminster Parliamentary Constituency boundary shapefile component.",
    },
    {
        "path": "data/shapefile/2024/PCON_JULY_2024_UK_BFC.shp",
        "sha256": "b2554563646912c1d86453ea86eaf8ad906aaaf6c337d5112a436d68ffae91f2",
        "size": 142526368,
        "source": "https://geoportal.statistics.gov.uk/datasets/ons::pcon-july-2024-boundaries-uk-bfc",
        "download": None,
        "note": "ONS 2024 Parliamentary Constituency full-resolution clipped boundary shapefile component.",
    },
]

RAW_DATA_SOURCE_EXTRA_FILES = {
    "data/shapefile/2019/WPC_Dec_2019_GCB_UK.cpg": ("3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824", 5),
    "data/shapefile/2019/WPC_Dec_2019_GCB_UK.dbf": ("1e6c3e759d4b55153bbd35aba8a09e5af7d910410d259d191f57ad449d870a5e", 97108),
    "data/shapefile/2019/WPC_Dec_2019_GCB_UK.prj": ("d97d276680377a05a19a8b8030ae04c4a87e883a9e5c07d0c646e5402e773a89", 417),
    "data/shapefile/2019/WPC_Dec_2019_GCB_UK.shp.xml": ("f056803a2c0d7d7b0f823cdd85dd623b9d3e282d777f22dc0bf82035f7b18c87", 250),
    "data/shapefile/2019/WPC_Dec_2019_GCB_UK.shx": ("b6fa747cef3008bd91620de1bde1a34f39e27fd8809f4e69f28880df6bc19372", 5300),
    "data/shapefile/2024/PCON_JULY_2024_UK_BFC.cpg": ("3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824", 5),
    "data/shapefile/2024/PCON_JULY_2024_UK_BFC.dbf": ("58146400af6d0db770afe429e59008c12db988fcff9529cffe709c68c79be95e", 108190),
    "data/shapefile/2024/PCON_JULY_2024_UK_BFC.prj": ("d97d276680377a05a19a8b8030ae04c4a87e883a9e5c07d0c646e5402e773a89", 417),
    "data/shapefile/2024/PCON_JULY_2024_UK_BFC.shp.xml": ("2e96c9fd308c38a5680adf8d3e351d994e330298d02df8759af729a05683cddc", 222),
    "data/shapefile/2024/PCON_JULY_2024_UK_BFC.shx": ("38aab6e12c83ae3cfe5516803c9fd7c0649236a452c159882c34f856d35cc753", 5300),
}

EXPECTED_SUMMARY_TABLE_HASHES = {
    "2019": "97b368775048aafee48d17974b71b770163c420eed12b0fc8d7ebf42c724895b",
    "2024": "2252b88fb687769d70bb495898a3a5ec0a6b9e4100b42ab521239372f175e729",
}

PARTY_METADATA = {
    "Lab": {
        "label": "Labour",
        "axis_label": "Labour Vote Share",
        "slug": "labour",
    },
    "Con": {
        "label": "Conservative",
        "axis_label": "Conservative Vote Share",
        "slug": "conservative",
    },
    "Lib": {
        "label": "Liberal Democrat",
        "axis_label": "Liberal Democrat Vote Share",
        "slug": "liberal_democrat",
    },
    "Vote": {
        "label": "Turnout",
        "axis_label": "Turnout",
        "slug": "turnout",
    },
}


def _ensure_output_dirs():
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(value):
    chars = [character.lower() if character.isalnum() else "_" for character in value]
    return "_".join(part for part in "".join(chars).split("_") if part)


def _party_metadata_from_code_or_column(value, fallback_label=None):
    party_code = value.replace(" PC", "") if value.endswith(" PC") else value
    metadata = PARTY_METADATA.get(party_code)
    if metadata is not None:
        return party_code, metadata["label"], metadata["axis_label"], metadata["slug"]

    label = fallback_label or party_code
    return party_code, label, f"{label} Vote Share", _slugify(label)


def _save_figure(fig, stem):
    fig.savefig(FIGURES_DIR / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / f"{stem}.svg", bbox_inches="tight")


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_raw_file(url, path, normalize_newlines=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".download")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            data = response.read()
    except Exception as exc:
        raise RuntimeError(f"Could not download {url}") from exc
    if normalize_newlines:
        data = data.replace(b"\r\n", b"\n")
    tmp_path.write_bytes(data)
    tmp_path.replace(path)


def _read_json_url(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_ons_filter_output(download_id, path):
    _, output_id, filetype = download_id.split(":")
    output_url = f"https://api.beta.ons.gov.uk/v1/filter-outputs/{output_id}"
    metadata = {}
    for _ in range(24):
        metadata = _read_json_url(output_url)
        if filetype in metadata.get("downloads", {}):
            break
        time.sleep(5)
    if filetype not in metadata.get("downloads", {}):
        state = metadata.get("state", "unknown")
        raise RuntimeError(f"ONS filter output {output_id} has no {filetype} download; state={state}.")
    download_url = metadata["downloads"][filetype]["href"]
    _download_raw_file(download_url, path)


def _download_ons_custom_filter(download_id, path):
    _, dataset_id, edition, version, area_dimension, measure_dimension, filetype = (
        download_id.split(":")
    )
    payload = {
        "dataset": {
            "id": dataset_id,
            "edition": edition,
            "version": int(version),
        },
        "population_type": "UR",
        "dimensions": [
            {"name": area_dimension, "is_area_type": True},
            {"name": measure_dimension},
        ],
    }
    filter_data = _read_json_url("https://api.beta.ons.gov.uk/v1/filters", payload)
    output_data = _read_json_url(
        f"https://api.beta.ons.gov.uk/v1/filters/{filter_data['filter_id']}/submit",
        {},
    )
    _download_ons_filter_output(
        f"ons_filter_output:{output_data['filter_output_id']}:{filetype}",
        path,
    )


def _download_arcgis_lookup(download_id, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if download_id == "arcgis:oa11_lsoa11_lookup":
        _read_arcgis_lookup(
            path,
            (
                "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
                "OA11_LSOA11_MSOA11_LAD11_EW_LUv2_b3fe7c68f4b2420185eaff6284d4c125/"
                "FeatureServer/0/query"
            ),
            ["OA11CD", "LSOA11CD"],
        )
    elif download_id == "arcgis:oa11_pcon11_lookup":
        _read_arcgis_lookup(
            path,
            (
                "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
                "OA11_PCON11_EER11_EW_LU_529f687ffa0e4f408c9968ae92435e8c/"
                "FeatureServer/0/query"
            ),
            ["OA11CD", "PCON11CD", "PCON11NM"],
        )
    else:
        raise ValueError(f"Unknown ArcGIS download id: {download_id}")


def _verify_file(path, expected_sha256, expected_size):
    if not path.exists():
        raise FileNotFoundError(f"Missing required data file: {path}")
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(
            f"{path} has size {actual_size}, expected {expected_size}. "
            "Do not continue because the analysis input changed."
        )
    actual_sha256 = _sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"{path} has sha256 {actual_sha256}, expected {expected_sha256}. "
            "Do not continue because the analysis input changed."
        )


def _raw_data_file_specs():
    specs = list(RAW_DATA_SOURCES)
    for path, (sha256, size) in RAW_DATA_SOURCE_EXTRA_FILES.items():
        specs.append({"path": path, "sha256": sha256, "size": size, "download": None})
    return specs


def ensure_raw_data(download=True, verify=True):
    """Fetch missing direct-download inputs and verify every raw file used by the analysis."""
    failures = []
    for spec in _raw_data_file_specs():
        path = PROJECT_ROOT / spec["path"]
        if download and not path.exists():
            download_url = spec.get("download")
            if isinstance(download_url, str) and download_url.startswith("arcgis:"):
                _download_arcgis_lookup(download_url, path)
            elif isinstance(download_url, str) and download_url.startswith("ons_filter_output:"):
                _download_ons_filter_output(download_url, path)
            elif isinstance(download_url, str) and download_url.startswith("ons_custom_filter:"):
                _download_ons_custom_filter(download_url, path)
            elif download_url:
                _download_raw_file(
                    download_url,
                    path,
                    normalize_newlines=spec.get("normalize_newlines", False),
                )
            else:
                failures.append(
                    f"{spec['path']} is missing and has no stable direct-download URL. "
                    f"Source: {spec.get('source', 'not recorded')}"
                )

    if failures:
        raise FileNotFoundError("\n".join(failures))

    if verify:
        for spec in _raw_data_file_specs():
            _verify_file(PROJECT_ROOT / spec["path"], spec["sha256"], spec["size"])
        validate_raw_data_schema()

    print("Raw data files are present and match the pinned checksums.")


def validate_raw_data_schema():
    expected = [
        ("data/raw/voting/HoC-GE2019-results-by-constituency.xlsx", "Data", 650, ["ONS ID", "First party", "Valid votes", "BRX"], {}),
        ("data/raw/voting/HoC-GE2024-results-by-constituency.xlsx", "Data", 650, ["ONS ID", "First party", "Valid votes", "RUK"], {}),
        ("data/raw/mortality/pcondeathspopulations20192024.xlsx", "Table 1", 573, ["Parliamentary Constituency Code ", "ASMR"], {"skiprows": 5}),
        ("data/raw/mortality/pcondeathspopulations20192024.xlsx", "Table 3", 575, ["Parliamentary Constituency Code ", "ASMR"], {"skiprows": 5}),
        ("data/raw/deprivation/deprivation_2025.xlsx", "Data_constituencies", 543, ["ONSConstID", "Health deprivation and disability"], {}),
        ("data/raw/life_expectancy/trends_in_sii.xlsx", "Sheet1", 36, ["timeperiod", "sex", "value"], {}),
    ]
    for rel_path, sheet_name, rows, columns, read_kwargs in expected:
        df = pd.read_excel(PROJECT_ROOT / rel_path, sheet_name=sheet_name, **read_kwargs)
        if len(df) != rows:
            raise ValueError(f"{rel_path} has {len(df)} rows; expected {rows}.")
        missing = [column for column in columns if column not in df.columns]
        if missing:
            raise ValueError(f"{rel_path} is missing columns: {missing}")

    csv_expected = {
        "data/raw/census/2019_health.csv": (1719, ["Westminster Parliamentary constituencies Code", "General health (3 categories)", "Observation"]),
        "data/raw/census/2024_health.csv": (1725, ["Post-2019 Westminster Parliamentary constituencies Code", "General health (3 categories)", "Observation"]),
        "data/raw/deprivation/File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv": (32844, ["LSOA code (2011)", "Health Deprivation and Disability Score"]),
        "data/raw/life_expectancy/HID_data_Life expectancy and mortality.csv": (50346, ["Indicator", "Category", "Time period", "Value"]),
    }
    for rel_path, (rows, columns) in csv_expected.items():
        df = pd.read_csv(PROJECT_ROOT / rel_path)
        if len(df) != rows:
            raise ValueError(f"{rel_path} has {len(df)} rows; expected {rows}.")
        missing = [column for column in columns if column not in df.columns]
        if missing:
            raise ValueError(f"{rel_path} is missing columns: {missing}")

    census_workbooks = {
        "data/raw/census/2019_disability.xlsx": (1719, "Westminster Parliamentary constituencies Code", "Disability (3 categories)"),
        "data/raw/census/2019_unpaid_care.xlsx": (2865, "Westminster Parliamentary constituencies Code", "Unpaid care (5 categories)"),
        "data/raw/census/2024_disability.xlsx": (1725, "Post-2019 Westminster Parliamentary constituencies Code", "Disability (3 categories)"),
        "data/raw/census/2024_unpaid_care.xlsx": (2875, "Post-2019 Westminster Parliamentary constituencies Code", "Unpaid care (5 categories)"),
    }
    for rel_path, (rows, code_col, category_col) in census_workbooks.items():
        df = pd.read_excel(PROJECT_ROOT / rel_path, sheet_name="Dataset")
        if len(df) != rows:
            raise ValueError(f"{rel_path} has {len(df)} rows; expected {rows}.")
        missing = [column for column in [code_col, category_col, "Observation"] if column not in df.columns]
        if missing:
            raise ValueError(f"{rel_path} is missing columns: {missing}")

    shapefiles = {
        "data/shapefile/2019/WPC_Dec_2019_GCB_UK.shp": (650, ["pcon19cd", "pcon19nm"]),
        "data/shapefile/2024/PCON_JULY_2024_UK_BFC.shp": (650, ["PCON24CD", "PCON24NM"]),
    }
    for rel_path, (rows, columns) in shapefiles.items():
        gdf = gpd.read_file(PROJECT_ROOT / rel_path)
        if len(gdf) != rows:
            raise ValueError(f"{rel_path} has {len(gdf)} rows; expected {rows}.")
        missing = [column for column in columns if column not in gdf.columns]
        if missing:
            raise ValueError(f"{rel_path} is missing columns: {missing}")


def raw_data_sources_markdown(sources=None, include_shapefile_components=True):
    sources = RAW_DATA_SOURCES if sources is None else sources
    shapefile_sources = {
        "data/shapefile/2019/": "https://geoportal.statistics.gov.uk/datasets/ons::wpc-dec-2019-generalised-clipped-boundaries-uk",
        "data/shapefile/2024/": "https://geoportal.statistics.gov.uk/datasets/ons::pcon-july-2024-boundaries-uk-bfc",
    }
    rows = [
        "| Dataset | Pinned local file | Source | Data href or fetch recipe | SHA256 |",
        "|---|---|---|---|---|",
    ]
    for spec in sources:
        label = spec["path"].split("/")[-1]
        source = spec.get("source")
        source_link = f"[source]({source})" if source else ""
        download = spec.get("download")
        if isinstance(download, str) and download.startswith("arcgis:"):
            data_href = download
        elif isinstance(download, str) and download.startswith("ons_filter_output:"):
            _, output_id, filetype = download.split(":")
            data_href = (
                f"[ONS filter output](https://api.beta.ons.gov.uk/v1/filter-outputs/{output_id}) "
                f"`{filetype}`"
            )
        elif isinstance(download, str) and download.startswith("ons_custom_filter:"):
            data_href = f"`{download}`"
        elif download:
            data_href = f"[data file]({download})"
        else:
            data_href = "pinned local file"
        rows.append(
            f"| {label} | `{spec['path']}` | {source_link} | {data_href} | `{spec['sha256']}` |"
        )
    if include_shapefile_components:
        for path, (sha256, _) in RAW_DATA_SOURCE_EXTRA_FILES.items():
            source = next(
                source for prefix, source in shapefile_sources.items() if path.startswith(prefix)
            )
            rows.append(
                f"| {path.split('/')[-1]} | `{path}` | [source]({source}) | pinned local file | `{sha256}` |"
            )
    return "\n".join(rows)


def main_analysis_data_sources_markdown():
    main_prefixes = (
        "data/raw/census/",
        "data/raw/deprivation/",
        "data/raw/mortality/",
        "data/raw/voting/",
    )
    sources = [spec for spec in RAW_DATA_SOURCES if spec["path"].startswith(main_prefixes)]
    return raw_data_sources_markdown(sources, include_shapefile_components=False)


def validate_summary_table_hash(table, year):
    """Fail if the final correlation table differs from the pinned current result."""
    key = str(year)
    expected = EXPECTED_SUMMARY_TABLE_HASHES[key]
    payload = table.round(12).to_csv(index=False).encode()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(
            f"{year} summary correlation table hash changed: {actual}; expected {expected}."
        )
    print(f"{year} summary correlation table matches pinned hash {expected}.")


def _find_column(df, candidates, label):
    for column in candidates:
        if column in df.columns:
            return column
    raise KeyError(f"Could not find {label}. Available columns: {list(df.columns)}")


def _read_arcgis_lookup(cache_path, service_url, fields):
    if cache_path.exists():
        return pd.read_csv(cache_path, dtype=str)

    records = []
    page_size = 2000
    offset = 0
    while True:
        params = urllib.parse.urlencode(
            {
                "where": "1=1",
                "outFields": ",".join(fields),
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "json",
            }
        )
        with urllib.request.urlopen(f"{service_url}?{params}") as response:
            payload = json.load(response)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        features = payload.get("features", [])
        if not features:
            break
        records.extend(feature["attributes"] for feature in features)
        if len(features) < page_size:
            break
        offset += page_size

    lookup = pd.DataFrame.from_records(records)
    lookup.to_csv(cache_path, index=False)
    return lookup


def make_2019_health_deprivation_from_lsoas():
    deprivation_path = RAW_DIR / "deprivation"
    iod_lsoa_candidates = [
        deprivation_path / "File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv",
        deprivation_path / "IoD2019_Scores_Ranks_Deciles_and_Population_Denominators.csv",
        deprivation_path / "IoD2019.csv",
    ]
    iod_lsoa_url = (
        "https://assets.publishing.service.gov.uk/government/uploads/"
        "system/uploads/attachment_data/file/845345/"
        "File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv"
    )
    oa_lsoa_cache = deprivation_path / "oa11_lsoa11_lookup.csv"
    oa_pcon_cache = deprivation_path / "oa11_pcon11_lookup.csv"
    oa_lsoa_service_url = (
        "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "OA11_LSOA11_MSOA11_LAD11_EW_LUv2_b3fe7c68f4b2420185eaff6284d4c125/"
        "FeatureServer/0/query"
    )
    oa_pcon_service_url = (
        "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
        "OA11_PCON11_EER11_EW_LU_529f687ffa0e4f408c9968ae92435e8c/"
        "FeatureServer/0/query"
    )

    iod_lsoa_path = next((path for path in iod_lsoa_candidates if path.exists()), None)
    if iod_lsoa_path is None:
        deprivation_path.mkdir(parents=True, exist_ok=True)
        iod_lsoa = pd.read_csv(iod_lsoa_url)
        iod_lsoa.to_csv(iod_lsoa_candidates[0], index=False)
    else:
        iod_lsoa = pd.read_csv(iod_lsoa_path)

    oa_lsoa = _read_arcgis_lookup(
        oa_lsoa_cache,
        oa_lsoa_service_url,
        ["OA11CD", "LSOA11CD"],
    )[["OA11CD", "LSOA11CD"]]
    oa_pcon = _read_arcgis_lookup(
        oa_pcon_cache,
        oa_pcon_service_url,
        ["OA11CD", "PCON11CD", "PCON11NM"],
    )[["OA11CD", "PCON11CD", "PCON11NM"]]

    lsoa_pcon_votes = pd.merge(
        oa_lsoa,
        oa_pcon,
        how="inner",
        on="OA11CD",
        validate="one_to_one",
    )
    lsoa_pcon = (
        lsoa_pcon_votes.groupby(["LSOA11CD", "PCON11CD", "PCON11NM"])
        .size()
        .reset_index(name="OACount")
        .sort_values(
            ["LSOA11CD", "OACount", "PCON11CD"],
            ascending=[True, False, True],
        )
        .drop_duplicates("LSOA11CD")
        .rename(columns={"PCON11CD": "ONS ID", "PCON11NM": "ConstituencyName"})
    )

    iod_lsoa_col = _find_column(
        iod_lsoa,
        ["LSOA code (2011)", "LSOA01CD"],
        "LSOA code in IoD2019 file",
    )
    health_score_col = _find_column(
        iod_lsoa,
        ["Health Deprivation and Disability Score", "HDDScore"],
        "health deprivation score",
    )
    health_rank_col = _find_column(
        iod_lsoa,
        ["Health Deprivation and Disability Rank (where 1 is most deprived)", "HDDRank"],
        "health deprivation rank",
    )
    population_col = _find_column(
        iod_lsoa,
        ["Total population: mid 2015 (excluding prisoners)", "TotPop"],
        "population denominator",
    )

    health_lsoa = iod_lsoa[
        [iod_lsoa_col, health_score_col, health_rank_col, population_col]
    ].rename(
        columns={
            iod_lsoa_col: "LSOA11CD",
            health_score_col: "HealthDeprivationAndDisabilityScore",
            health_rank_col: "HealthDeprivationAndDisabilityLSOARank",
            population_col: "HealthDeprivationAndDisabilityPopulation",
        }
    )
    for column in [
        "HealthDeprivationAndDisabilityScore",
        "HealthDeprivationAndDisabilityLSOARank",
        "HealthDeprivationAndDisabilityPopulation",
    ]:
        health_lsoa[column] = pd.to_numeric(health_lsoa[column], errors="coerce")

    deprivation_lsoa = pd.merge(
        health_lsoa,
        lsoa_pcon,
        how="left",
        on="LSOA11CD",
        validate="many_to_one",
    )
    if deprivation_lsoa["ONS ID"].isna().any():
        missing = deprivation_lsoa.loc[
            deprivation_lsoa["ONS ID"].isna(),
            "LSOA11CD",
        ].head().tolist()
        raise ValueError(f"IoD2019 LSOAs missing from ONS PCON lookup: {missing}")

    def weighted_mean(group, value_col):
        values = group[value_col]
        weights = group["HealthDeprivationAndDisabilityPopulation"]
        valid = values.notna() & weights.notna() & (weights > 0)
        if valid.any():
            return np.average(values[valid], weights=weights[valid])
        return values.mean()

    rows = []
    for (ons_id, constituency_name), group in deprivation_lsoa.groupby(
        ["ONS ID", "ConstituencyName"]
    ):
        rows.append(
            {
                "ONS ID": ons_id,
                "ConstituencyName": constituency_name,
                "HealthDeprivationAndDisabilityScore": weighted_mean(
                    group,
                    "HealthDeprivationAndDisabilityScore",
                ),
                "HealthDeprivationAndDisabilityLSOARankMean": weighted_mean(
                    group,
                    "HealthDeprivationAndDisabilityLSOARank",
                ),
                "HealthDeprivationAndDisabilityLSOACount": group["LSOA11CD"].nunique(),
            }
        )

    deprivation_pcon = pd.DataFrame(rows)
    deprivation_pcon["HealthDeprivationAndDisabilityRank"] = (
        deprivation_pcon["HealthDeprivationAndDisabilityScore"]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )
    return deprivation_pcon[
        [
            "ONS ID",
            "HealthDeprivationAndDisabilityRank",
            "HealthDeprivationAndDisabilityScore",
            "HealthDeprivationAndDisabilityLSOARankMean",
            "HealthDeprivationAndDisabilityLSOACount",
        ]
    ]


def make_census_percentages(year):
    if year == 2019:
        code_col = "Westminster Parliamentary constituencies Code"
    elif year == 2024:
        code_col = "Post-2019 Westminster Parliamentary constituencies Code"
    else:
        raise ValueError("year must be 2019 or 2024")

    census_path = RAW_DIR / "census"
    health = pd.read_csv(census_path / f"{year}_health.csv")
    disability = pd.read_excel(census_path / f"{year}_disability.xlsx")
    unpaid_care = pd.read_excel(census_path / f"{year}_unpaid_care.xlsx")

    def category_proportions(df, category_col, output_specs):
        pivot = df.pivot_table(
            index=code_col,
            columns=category_col,
            values="Observation",
            aggfunc="sum",
            fill_value=0,
        )
        result = pd.DataFrame(index=pivot.index)
        all_denominator_categories = sorted(
            {
                category
                for _, _, denominator_categories in output_specs
                for category in denominator_categories
            }
        )
        pivot = pivot.reindex(columns=all_denominator_categories, fill_value=0)

        for output_column, numerator_categories, denominator_categories in output_specs:
            numerator = pivot.reindex(
                columns=numerator_categories,
                fill_value=0,
            ).sum(axis=1)
            denominator = pivot.reindex(
                columns=denominator_categories,
                fill_value=0,
            ).sum(axis=1)
            result[output_column] = numerator / denominator.replace(0, np.nan)

        return result.reset_index().rename(columns={code_col: "ONS ID"})

    health_categories = ["Good health", "Not good health"]
    health_props = category_proportions(
        health,
        "General health (3 categories)",
        [
            ("ProportionGoodHealth", ["Good health"], health_categories),
            ("ProportionBadHealth", ["Not good health"], health_categories),
        ],
    )

    disability_categories = [
        "Disabled under the Equality Act",
        "Not disabled under the Equality Act",
    ]
    disability_props = category_proportions(
        disability,
        "Disability (3 categories)",
        [
            (
                "ProportionDisabled",
                ["Disabled under the Equality Act"],
                disability_categories,
            ),
            (
                "ProportionNotDisabled",
                ["Not disabled under the Equality Act"],
                disability_categories,
            ),
        ],
    )

    unpaid_care_no = ["Provides no unpaid care"]
    unpaid_care_any = [
        "Provides 19 or less hours unpaid care a week",
        "Provides 20 to 49 hours unpaid care a week",
        "Provides 50 or more hours unpaid care a week",
    ]
    unpaid_care_categories = unpaid_care_no + unpaid_care_any
    unpaid_care_props = category_proportions(
        unpaid_care,
        "Unpaid care (5 categories)",
        [
            ("ProportionProvidesNoUnpaidCare", unpaid_care_no, unpaid_care_categories),
            ("ProportionProvidesAnyUnpaidCare", unpaid_care_any, unpaid_care_categories),
            (
                "ProportionProvides19OrLessHoursUnpaidCare",
                ["Provides 19 or less hours unpaid care a week"],
                unpaid_care_categories,
            ),
            (
                "ProportionProvides20To49HoursUnpaidCare",
                ["Provides 20 to 49 hours unpaid care a week"],
                unpaid_care_categories,
            ),
            (
                "ProportionProvides50OrMoreHoursUnpaidCare",
                ["Provides 50 or more hours unpaid care a week"],
                unpaid_care_categories,
            ),
        ],
    )

    census = pd.merge(health_props, disability_props, how="left", on="ONS ID")
    return pd.merge(census, unpaid_care_props, how="left", on="ONS ID")


def make_deprivation_health_rank(year):
    if year == 2019:
        return make_2019_health_deprivation_from_lsoas()
    if year != 2024:
        raise ValueError("year must be 2019 or 2024")

    deprivation = pd.read_excel(
        RAW_DIR / "deprivation" / "deprivation_2025.xlsx",
        sheet_name="Data_constituencies",
    )
    return deprivation[["ONSConstID", "Health deprivation and disability"]].rename(
        columns={
            "ONSConstID": "ONS ID",
            "Health deprivation and disability": "HealthDeprivationAndDisabilityRank",
        }
    )


def make_merged(year):
    if year == 2019:
        sheet_start = 1
    elif year == 2024:
        sheet_start = 3
    else:
        raise ValueError("year must be 2019 or 2024")

    df_voting = pd.read_excel(
        RAW_DIR / "voting" / f"HoC-GE{year}-results-by-constituency.xlsx",
        sheet_name="Data",
    )
    mortality_fname = "pcondeathspopulations20192024.xlsx"
    df_mortality_m = pd.read_excel(
        RAW_DIR / "mortality" / mortality_fname,
        sheet_name=f"Table {sheet_start}",
        skiprows=5,
    ).rename({"ASMR": "ASMR_m"}, axis=1)
    df_mortality_f = pd.read_excel(
        RAW_DIR / "mortality" / mortality_fname,
        sheet_name=f"Table {sheet_start + 1}",
        skiprows=5,
    ).rename({"ASMR": "ASMR_f"}, axis=1)

    asmr = pd.merge(
        df_mortality_m,
        df_mortality_f,
        how="left",
        on=["Parliamentary Constituency Code ", "Parliamentary Constituency Name"],
    )
    asmr = asmr[
        [
            "Parliamentary Constituency Name",
            "Parliamentary Constituency Code ",
            "ASMR_f",
            "ASMR_m",
        ]
    ]

    print("Note: dropping all constituencies that are outside of England here.")
    df_voting = df_voting[df_voting["Country name"] == "England"].copy()
    df_voting["Constituency name"] = (
        df_voting["Constituency name"]
        .str.title()
        .str.strip()
        .str.replace(r"[^a-zA-Z\s]", "", regex=True)
    )

    df_m = pd.merge(
        df_voting,
        asmr,
        how="left",
        left_on="ONS ID",
        right_on="Parliamentary Constituency Code ",
    )
    df_m = pd.merge(df_m, make_census_percentages(year), how="left", on="ONS ID")
    df_m = pd.merge(df_m, make_deprivation_health_rank(year), how="left", on="ONS ID")

    df_m["Con PC"] = df_m["Con"] / df_m["Valid votes"]
    df_m["Lab PC"] = df_m["Lab"] / df_m["Valid votes"]
    df_m["Lib PC"] = df_m["LD"] / df_m["Valid votes"]
    df_m["Vote PC"] = (df_m["Valid votes"] + df_m["Invalid votes"]) / df_m["Electorate"]
    if year == 2019:
        df_m["Brx PC"] = df_m["BRX"] / df_m["Valid votes"]
    else:
        df_m["RUK PC"] = df_m["RUK"] / df_m["Valid votes"]
    df_m["first_party_3"] = np.where(
        (df_m["First party"] == "Lab") | (df_m["First party"] == "Con"),
        df_m["First party"],
        "Other",
    )
    return df_m


def make_df_gpd(year, df):
    if year == 2019:
        border = gpd.read_file(
            DATA_DIR / "shapefile" / "2019" / "WPC_Dec_2019_GCB_UK.shp"
        )
        df_gpd = pd.merge(
            border,
            df,
            how="left",
            left_on="pcon19cd",
            right_on="ONS ID",
        )
    elif year == 2024:
        border = gpd.read_file(
            DATA_DIR / "shapefile" / "2024" / "PCON_JULY_2024_UK_BFC.shp"
        )
        df_gpd = pd.merge(
            border,
            df,
            how="left",
            left_on="PCON24CD",
            right_on="ONS ID",
        )
    else:
        raise ValueError("year must be 2019 or 2024")

    df_gpd = gpd.GeoDataFrame(df_gpd)
    df_gpd = df_gpd.set_geometry("geometry")
    df_gpd["geometry"] = df_gpd["geometry"].simplify(
        tolerance=400,
        preserve_topology=True,
    )
    return df_gpd


def print_mean_ASMRs(df_2019, df_2024):
    for year, df in [(2019, df_2019), (2024, df_2024)]:
        for sex, column in [("men", "ASMR_m"), ("women", "ASMR_f")]:
            for party_label, party in [
                ("Labour", "Lab"),
                ("Conservative", "Con"),
                ("Other party", "Other"),
            ]:
                mean_value = df[df["first_party_3"] == party][column].mean()
                print(
                    f"{party_label} mean ASMR for {sex} in {year}: ",
                    np.round(mean_value, 3),
                )


def _mortality_sheet(year, sex):
    sheets = {
        2019: {"male": "Table 1", "female": "Table 2"},
        2024: {"male": "Table 3", "female": "Table 4"},
    }
    return sheets[year][sex]


def _get_asmr_ci(year, constituency, sex):
    df = pd.read_excel(
        RAW_DIR / "mortality" / "pcondeathspopulations20192024.xlsx",
        sheet_name=_mortality_sheet(year, sex),
        skiprows=5,
    )
    match = df[df["Parliamentary Constituency Name"].eq(constituency)]
    if match.empty:
        raise KeyError(f"Could not find {constituency} in mortality table for {year}.")

    row = match.iloc[0]
    return {
        "ASMR": row["ASMR"],
        "CI Lower": row["CI Lower"],
        "CI Upper": row["CI Upper"],
    }


def make_leader_asmr_table():
    leader_constituencies = {
        2019: [
            ("Rishi Sunak", "Conservative", "Richmond (Yorks)"),
            ("Keir Starmer", "Labour", "Holborn and St Pancras"),
        ],
        2024: [
            ("Rishi Sunak", "Conservative", "Richmond and Northallerton"),
            ("Keir Starmer", "Labour", "Holborn and St Pancras"),
        ],
    }

    rows = []
    for year, leaders in leader_constituencies.items():
        for leader, party, constituency in leaders:
            for sex in ["female", "male"]:
                values = _get_asmr_ci(year, constituency, sex)
                rows.append(
                    {
                        "Year": year,
                        "Leader": leader,
                        "Party": party,
                        "Constituency": constituency,
                        "Sex": sex.title(),
                        **values,
                    }
                )
    return pd.DataFrame(rows)


def _format_asmr_ci(row):
    return (
        f"{row['ASMR']:.1f} "
        f"(95% CI {row['CI Lower']:.1f}-{row['CI Upper']:.1f})"
    )


def _summary_table_coefficient(table, statistic, variable, column):
    match = table[
        (table["Statistic"] == statistic)
        & (table["Variable"] == variable)
    ]
    if match.empty:
        raise KeyError(f"Could not find {statistic} {variable} in summary table.")
    return float(match.iloc[0][column])


def print_manuscript_statistics(table_rho_2019, table_rho_2024):
    leader_asmr = make_leader_asmr_table()
    print(
        "Leader constituency ASMRs "
        "(ONS deaths registered; age-standardised rates per 100,000)"
    )
    for year in [2019, 2024]:
        print(f"\n{year} registered deaths and constituency boundaries:")
        rows = leader_asmr[leader_asmr["Year"] == year]
        for _, leader_row in rows.drop_duplicates("Leader").iterrows():
            leader = leader_row["Leader"]
            constituency = leader_row["Constituency"]
            leader_rows = rows[rows["Leader"] == leader].set_index("Sex")
            female = _format_asmr_ci(leader_rows.loc["Female"])
            male = _format_asmr_ci(leader_rows.loc["Male"])
            print(f"{leader}, {constituency}: female {female}; male {male}.")

    tables = {2019: table_rho_2019, 2024: table_rho_2024}
    print("\nLabour vote-share correlations with ASMR")
    for sex_label, variable in [("Male", "ASMR_m"), ("Female", "ASMR_f")]:
        spearman_2019 = _summary_table_coefficient(
            tables[2019], "Spearman", variable, "Lab PC"
        )
        spearman_2024 = _summary_table_coefficient(
            tables[2024], "Spearman", variable, "Lab PC"
        )
        pearson_2019 = _summary_table_coefficient(
            tables[2019], "Pearson", variable, "Lab PC"
        )
        pearson_2024 = _summary_table_coefficient(
            tables[2024], "Pearson", variable, "Lab PC"
        )
        print(
            f"{sex_label} ASMR: Spearman rho = {spearman_2019:.3f} (2019), "
            f"{spearman_2024:.3f} (2024); Pearson r = {pearson_2019:.3f} "
            f"(2019), {pearson_2024:.3f} (2024)."
        )


def print_p_value_table(table):
    p_value_columns = [
        column
        for column in table.columns
        if column not in {"Statistic", "Variable", "Year", "N"}
    ]
    display_table = table.copy()
    for column in p_value_columns:
        display_table[column] = display_table[column].map(
            lambda value: f"{float(value):.3g}"
        )
    print(display_table.to_string(index=False))


def _correlation_value_columns(table):
    metadata_columns = {"Statistic", "Variable", "Year", "N"}
    return [column for column in table.columns if column not in metadata_columns]


def _format_publication_p_value(p_value):
    p_value = float(p_value)
    if p_value < 0.001:
        return "<0.001"
    return f"{p_value:.3f}".rstrip("0").rstrip(".")


def _format_coefficient_with_p_value(coefficient, p_value):
    return f"{float(coefficient):.3f} ({_format_publication_p_value(p_value)})"


PUBLICATION_VARIABLE_LABELS = {
    "ASMR_f": "ASMR, female",
    "ASMR_m": "ASMR, male",
    "ProportionBadHealth": "Not good health",
    "ProportionDisabled": "Disabled under Equality Act",
    "ProportionProvidesAnyUnpaidCare": "Any unpaid care",
    "HealthDeprivationAndDisabilityRank": "Health Deprivation and Disability rank",
}

PUBLICATION_CORRELATION_TABLE_COLUMN_LABELS = {
    "Statistic": "Correlation",
    "Variable": "Health/deprivation measure",
    "Year": "Year",
    "N": "N",
    "Con PC": "Conservative",
    "Lab PC": "Labour",
    "Lib PC": "Liberal Democrat",
    "Brx/RUK PC": "Brexit/Reform UK",
    "Vote PC": "Turnout",
}

DOCX_TABLE_COLUMN_WIDTHS = {
    "Correlation": 900,
    "Health/deprivation measure": 3300,
    "Year": 650,
    "N": 500,
    "Conservative": 2200,
    "Labour": 2200,
    "Liberal Democrat": 2200,
    "Brexit/Reform UK": 2200,
    "Turnout": 2200,
}

MANUSCRIPT_TABLE_MEASURES = [
    ("ASMR (female)", "ASMR_f"),
    ("ASMR (male)", "ASMR_m"),
    ("Not good health", "ProportionBadHealth"),
    ("Disability", "ProportionDisabled"),
]

MANUSCRIPT_TABLE_ROWS = [
    ("Conservative", {2019: "Con PC", 2024: "Con PC"}),
    ("Labour", {2019: "Lab PC", 2024: "Lab PC"}),
    ("Liberal Democrat", {2019: "Lib PC", 2024: "Lib PC"}),
    ("Brexit Party", {2019: "Brx PC", 2024: None}),
    ("Reform UK", {2019: None, 2024: "RUK PC"}),
    ("Voter turnout", {2019: "Vote PC", 2024: "Vote PC"}),
]

DOCX_MANUSCRIPT_COLUMN_WIDTHS = [1150, 1700] + [1700] * 8
DOCX_PORTRAIT_COLUMN_WIDTHS = [1900, 1500, 2800, 2400, 2400]


def make_combined_correlation_p_value_table(
    table_rho_2019,
    table_p_2019,
    table_rho_2024,
    table_p_2024,
):
    rows = []
    table_pairs = [
        (table_rho_2019, table_p_2019),
        (table_rho_2024, table_p_2024),
    ]

    for table_rho, table_p in table_pairs:
        p_lookup = table_p.set_index(["Statistic", "Variable"])
        for _, rho_row in table_rho.iterrows():
            key = (rho_row["Statistic"], rho_row["Variable"])
            p_row = p_lookup.loc[key]
            output_row = {
                "Statistic": rho_row["Statistic"],
                "Variable": PUBLICATION_VARIABLE_LABELS.get(
                    rho_row["Variable"],
                    rho_row["Variable"],
                ),
                "Year": rho_row["Year"],
                "N": rho_row["N"],
            }

            for column in _correlation_value_columns(table_rho):
                output_column = "Brx/RUK PC" if column in {"Brx PC", "RUK PC"} else column
                output_row[output_column] = _format_coefficient_with_p_value(
                    rho_row[column],
                    p_row[column],
                )
            rows.append(output_row)

    columns = [
        "Statistic",
        "Variable",
        "Year",
        "N",
        "Con PC",
        "Lab PC",
        "Lib PC",
        "Brx/RUK PC",
        "Vote PC",
    ]
    return (
        pd.DataFrame(rows)
        .reindex(columns=columns)
        .rename(columns=PUBLICATION_CORRELATION_TABLE_COLUMN_LABELS)
    )


def _format_manuscript_p_value(p_value):
    p_value = float(p_value)
    if p_value < 0.001:
        return "<0.001"
    return f"{p_value:.3f}".rstrip("0").rstrip(".")


def _format_manuscript_coefficient_with_p_value(coefficient, p_value):
    return f"{float(coefficient):.3f} ({_format_manuscript_p_value(p_value)})"


def _summary_table_row(table, statistic, variable):
    match = table[
        (table["Statistic"] == statistic)
        & (table["Variable"] == variable)
    ]
    if match.empty:
        raise KeyError(f"Could not find {statistic} {variable} in summary table.")
    return match.iloc[0]


def _manuscript_correlation_cell(tables, statistic, variable, year, column):
    if column is None:
        return ""
    rho_row = _summary_table_row(tables[year]["rho"], statistic, variable)
    p_row = _summary_table_row(tables[year]["p"], statistic, variable)
    return _format_manuscript_coefficient_with_p_value(
        rho_row[column],
        p_row[column],
    )


def make_manuscript_correlation_p_value_rows(
    table_rho_2019,
    table_p_2019,
    table_rho_2024,
    table_p_2024,
):
    tables = {
        2019: {"rho": table_rho_2019, "p": table_p_2019},
        2024: {"rho": table_rho_2024, "p": table_p_2024},
    }
    rows = []
    statistic_labels = [
        ("Spearman", "Spearman rho"),
        ("Pearson", "Pearson r"),
    ]

    for statistic, statistic_label in statistic_labels:
        for row_label, columns_by_year in MANUSCRIPT_TABLE_ROWS:
            row = [statistic_label, row_label]
            for _, variable in MANUSCRIPT_TABLE_MEASURES:
                for year in [2019, 2024]:
                    row.append(
                        _manuscript_correlation_cell(
                            tables,
                            statistic,
                            variable,
                            year,
                            columns_by_year[year],
                        )
                    )
            rows.append(row)

    n_row = ["", "N"]
    for _, variable in MANUSCRIPT_TABLE_MEASURES:
        for year in [2019, 2024]:
            n_row.append(
                str(_summary_table_row(tables[year]["rho"], "Spearman", variable)["N"])
            )
    rows.append(n_row)
    return rows


def make_portrait_correlation_p_value_rows(
    table_rho_2019,
    table_p_2019,
    table_rho_2024,
    table_p_2024,
):
    tables = {
        2019: {"rho": table_rho_2019, "p": table_p_2019},
        2024: {"rho": table_rho_2024, "p": table_p_2024},
    }
    rows = []
    statistic_labels = [
        ("Spearman", "Spearman rho"),
        ("Pearson", "Pearson r"),
    ]

    for measure_label, variable in MANUSCRIPT_TABLE_MEASURES:
        is_first_measure_row = True
        for statistic, statistic_label in statistic_labels:
            is_first_statistic_row = True
            for row_label, columns_by_year in MANUSCRIPT_TABLE_ROWS:
                rows.append(
                    [
                        measure_label if is_first_measure_row else "",
                        statistic_label if is_first_statistic_row else "",
                        row_label,
                        _manuscript_correlation_cell(
                            tables,
                            statistic,
                            variable,
                            2019,
                            columns_by_year[2019],
                        ),
                        _manuscript_correlation_cell(
                            tables,
                            statistic,
                            variable,
                            2024,
                            columns_by_year[2024],
                        ),
                    ]
                )
                is_first_measure_row = False
                is_first_statistic_row = False
        rows.append(
            [
                "",
                "N",
                "",
                str(_summary_table_row(tables[2019]["rho"], "Spearman", variable)["N"]),
                str(_summary_table_row(tables[2024]["rho"], "Spearman", variable)["N"]),
            ]
        )
    return rows


def _docx_run(text, bold=False, size=12):
    run_properties = (
        "<w:rFonts w:ascii=\"Arial Narrow\" w:hAnsi=\"Arial Narrow\" "
        "w:cs=\"Arial Narrow\"/>"
        f"<w:sz w:val=\"{size}\"/><w:szCs w:val=\"{size}\"/>"
    )
    if bold:
        run_properties = "<w:b/><w:bCs/>" + run_properties
    return (
        "<w:r>"
        f"<w:rPr>{run_properties}</w:rPr>"
        f"<w:t xml:space=\"preserve\">{escape(str(text))}</w:t>"
        "</w:r>"
    )


def _docx_paragraph(text="", bold=False, size=12):
    return (
        "<w:p>"
        "<w:pPr><w:spacing w:after=\"20\" w:line=\"140\" w:lineRule=\"exact\"/></w:pPr>"
        f"{_docx_run(text, bold=bold, size=size)}"
        "</w:p>"
    )


def _docx_cell(text, bold=False, width=None, grid_span=None, size=14):
    width_properties = ""
    if width is not None:
        width_properties = f"<w:tcW w:w=\"{width}\" w:type=\"dxa\"/>"
    grid_span_properties = ""
    if grid_span is not None:
        grid_span_properties = f"<w:gridSpan w:val=\"{grid_span}\"/>"
    return (
        "<w:tc>"
        "<w:tcPr>"
        f"{width_properties}"
        f"{grid_span_properties}"
        "<w:tcMar>"
        "<w:top w:w=\"20\" w:type=\"dxa\"/>"
        "<w:left w:w=\"20\" w:type=\"dxa\"/>"
        "<w:bottom w:w=\"20\" w:type=\"dxa\"/>"
        "<w:right w:w=\"20\" w:type=\"dxa\"/>"
        "</w:tcMar></w:tcPr>"
        "<w:p><w:pPr><w:spacing w:after=\"0\" w:line=\"120\" "
        "w:lineRule=\"exact\"/></w:pPr>"
        f"{_docx_run(text, bold=bold, size=size)}"
        "</w:p>"
        "</w:tc>"
    )


def _docx_table(table):
    borders = "".join(
        f"<w:{side} w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        for side in ["top", "left", "bottom", "right", "insideH", "insideV"]
    )
    column_widths = [DOCX_TABLE_COLUMN_WIDTHS[column] for column in table.columns]
    rows = [
        "<w:tr><w:trPr><w:trHeight w:val=\"180\" w:hRule=\"atLeast\"/></w:trPr>"
        + "".join(
            _docx_cell(column, bold=True, width=column_widths[index])
            for index, column in enumerate(table.columns)
        )
        + "</w:tr>"
    ]
    for _, row in table.iterrows():
        rows.append(
            "<w:tr><w:trPr><w:trHeight w:val=\"180\" w:hRule=\"atLeast\"/></w:trPr>"
            + "".join(
                _docx_cell(row[column], width=column_widths[index])
                for index, column in enumerate(table.columns)
            )
            + "</w:tr>"
        )
    return (
        "<w:tbl>"
        "<w:tblPr>"
        "<w:tblW w:w=\"16478\" w:type=\"dxa\"/>"
        "<w:tblLayout w:type=\"fixed\"/>"
        f"<w:tblBorders>{borders}</w:tblBorders>"
        "</w:tblPr>"
        + "".join(rows)
        + "</w:tbl>"
    )


def _docx_row(cells, height=180):
    return (
        f"<w:tr><w:trPr><w:trHeight w:val=\"{height}\" "
        "w:hRule=\"atLeast\"/></w:trPr>"
        + "".join(cells)
        + "</w:tr>"
    )


def _docx_manuscript_table(rows):
    borders = "".join(
        f"<w:{side} w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        for side in ["top", "left", "bottom", "right", "insideH", "insideV"]
    )
    table_grid = "<w:tblGrid>" + "".join(
        f"<w:gridCol w:w=\"{width}\"/>" for width in DOCX_MANUSCRIPT_COLUMN_WIDTHS
    ) + "</w:tblGrid>"

    header_1 = [
        _docx_cell("Correlation", bold=True, width=DOCX_MANUSCRIPT_COLUMN_WIDTHS[0]),
        _docx_cell(
            "Political party/measure",
            bold=True,
            width=DOCX_MANUSCRIPT_COLUMN_WIDTHS[1],
        ),
    ]
    for measure_label, _ in MANUSCRIPT_TABLE_MEASURES:
        header_1.append(
            _docx_cell(
                measure_label,
                bold=True,
                width=sum(DOCX_MANUSCRIPT_COLUMN_WIDTHS[2:4]),
                grid_span=2,
            )
        )

    header_2 = [
        _docx_cell("", width=DOCX_MANUSCRIPT_COLUMN_WIDTHS[0]),
        _docx_cell("", width=DOCX_MANUSCRIPT_COLUMN_WIDTHS[1]),
    ]
    for index in range(2, len(DOCX_MANUSCRIPT_COLUMN_WIDTHS), 2):
        header_2.extend(
            [
                _docx_cell("2019", bold=True, width=DOCX_MANUSCRIPT_COLUMN_WIDTHS[index]),
                _docx_cell("2024", bold=True, width=DOCX_MANUSCRIPT_COLUMN_WIDTHS[index + 1]),
            ]
        )

    table_rows = [_docx_row(header_1), _docx_row(header_2)]
    for row in rows:
        table_rows.append(
            _docx_row(
                [
                    _docx_cell(value, width=DOCX_MANUSCRIPT_COLUMN_WIDTHS[index])
                    for index, value in enumerate(row)
                ]
            )
        )

    return (
        "<w:tbl>"
        "<w:tblPr>"
        "<w:tblW w:w=\"16450\" w:type=\"dxa\"/>"
        "<w:tblLayout w:type=\"fixed\"/>"
        f"<w:tblBorders>{borders}</w:tblBorders>"
        "</w:tblPr>"
        + table_grid
        + "".join(table_rows)
        + "</w:tbl>"
    )


def _docx_portrait_table(rows):
    borders = "".join(
        f"<w:{side} w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        for side in ["top", "left", "bottom", "right", "insideH", "insideV"]
    )
    table_grid = "<w:tblGrid>" + "".join(
        f"<w:gridCol w:w=\"{width}\"/>" for width in DOCX_PORTRAIT_COLUMN_WIDTHS
    ) + "</w:tblGrid>"
    header = [
        _docx_cell(column, bold=True, width=DOCX_PORTRAIT_COLUMN_WIDTHS[index], size=12)
        for index, column in enumerate(
            ["Outcome", "Statistic", "Political party/measure", "2019", "2024"]
        )
    ]
    table_rows = [_docx_row(header, height=150)]
    for row in rows:
        table_rows.append(
            _docx_row(
                [
                    _docx_cell(value, width=DOCX_PORTRAIT_COLUMN_WIDTHS[index], size=12)
                    for index, value in enumerate(row)
                ],
                height=150,
            )
        )

    return (
        "<w:tbl>"
        "<w:tblPr>"
        f"<w:tblW w:w=\"{sum(DOCX_PORTRAIT_COLUMN_WIDTHS)}\" w:type=\"dxa\"/>"
        "<w:tblLayout w:type=\"fixed\"/>"
        f"<w:tblBorders>{borders}</w:tblBorders>"
        "</w:tblPr>"
        + table_grid
        + "".join(table_rows)
        + "</w:tbl>"
    )


def _write_docx_table(path, title, notes, table, orientation="landscape"):
    table_xml = table if isinstance(table, str) else _docx_table(table)
    if orientation == "portrait":
        page_size_xml = "<w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
    elif orientation == "landscape":
        page_size_xml = "<w:pgSz w:w=\"16838\" w:h=\"11906\" w:orient=\"landscape\"/>"
    else:
        raise ValueError(f"Unsupported DOCX orientation: {orientation}")
    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        "<w:body>"
        f"{_docx_paragraph(title, bold=True, size=16)}"
        + "".join(_docx_paragraph(note, size=10) for note in notes)
        + table_xml
        + "<w:sectPr>"
        f"{page_size_xml}"
        "<w:pgMar w:top=\"180\" w:right=\"180\" w:bottom=\"180\" "
        "w:left=\"180\" w:header=\"180\" w:footer=\"180\" w:gutter=\"0\"/>"
        "</w:sectPr>"
        "</w:body>"
        "</w:document>"
    )
    content_types = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" "
        "ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/word/document.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document.main+xml\"/>"
        "</Types>"
    )
    relationships = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships "
        "xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" "
        "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
        "officeDocument\" Target=\"word/document.xml\"/>"
        "</Relationships>"
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", relationships)
        docx.writestr("word/document.xml", document_xml)


def export_correlation_tables_docx(
    table_rho_2019,
    table_p_2019,
    table_rho_2024,
    table_p_2024,
    filename="correlation_and_p_value_tables.docx",
):
    _ensure_output_dirs()
    manuscript_rows = make_manuscript_correlation_p_value_rows(
        table_rho_2019,
        table_p_2019,
        table_rho_2024,
        table_p_2024,
    )
    output_path = TABLES_DIR / filename
    _write_docx_table(
        output_path,
        "Table 1. Political party by mortality, health and disability",
        [
            "Cells show correlation coefficient (p value). ASMR denotes age-standardised mortality rate per 100,000 population.",
            "Party rows are vote shares except voter turnout; p values <0.001 are shown as <0.001.",
        ],
        _docx_manuscript_table(manuscript_rows),
        orientation="landscape",
    )
    print(f"Wrote {output_path}")
    return output_path


def export_full_correlation_tables_docx(
    table_rho_2019,
    table_p_2019,
    table_rho_2024,
    table_p_2024,
    filename="full_correlation_and_p_value_table.docx",
):
    _ensure_output_dirs()
    full_table = make_combined_correlation_p_value_table(
        table_rho_2019,
        table_p_2019,
        table_rho_2024,
        table_p_2024,
    )
    output_path = TABLES_DIR / filename
    _write_docx_table(
        output_path,
        "Supplementary table. Political party by mortality, health, unpaid care and deprivation",
        [
            "Cells show correlation coefficient (p value). ASMR denotes age-standardised mortality rate per 100,000 population.",
            "Party columns are vote shares except voter turnout; Brexit/Reform UK is Brexit Party in 2019 and Reform UK in 2024.",
            "P values <0.001 are shown as <0.001.",
        ],
        full_table,
        orientation="landscape",
    )
    print(f"Wrote {output_path}")
    return output_path


def plot_scatters(df_2019, df_2024, config_list):
    _ensure_output_dirs()
    df_2019 = df_2019[df_2019["First party"] != "Spk"].copy()
    df_2024 = df_2024[df_2024["First party"] != "Spk"].copy()
    df_2019 = df_2019[df_2019["ASMR_f"].notnull()]
    df_2024 = df_2024[df_2024["ASMR_f"].notnull()]
    print("The length of the 2019 data going into the scatters is: ", len(df_2019))
    print("The length of the 2024 data going into the scatters is: ", len(df_2024))

    fig = plt.figure(figsize=(12, 10))
    gs = grid_spec.GridSpec(2, 2)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0])
    ax4 = fig.add_subplot(gs[1, 1])
    axes = [ax1, ax2, ax3, ax4]

    color_mapping = {"Lab": "#E4003B", "Con": "#0087DC", "Other": "lightgrey"}
    df_2019["color"] = df_2019["first_party_3"].map(color_mapping)
    df_2024["color"] = df_2024["first_party_3"].map(color_mapping)
    party_column, fallback_label, annotate_leaders = config_list
    _, party_label, axis_label, party_slug = _party_metadata_from_code_or_column(
        party_column,
        fallback_label,
    )

    ax1.scatter(df_2019[party_column], df_2019["ASMR_f"], color=df_2019["color"], edgecolor="k")
    ax2.scatter(df_2019[party_column], df_2019["ASMR_m"], color=df_2019["color"], edgecolor="k")
    ax3.scatter(df_2024[party_column], df_2024["ASMR_f"], color=df_2024["color"], edgecolor="k")
    ax4.scatter(df_2024[party_column], df_2024["ASMR_m"], color=df_2024["color"], edgecolor="k")

    ax1.set_ylabel("ASMR (Female)", fontsize=14)
    ax2.set_ylabel("ASMR (Male)", fontsize=14)
    ax3.set_ylabel("ASMR (Female)", fontsize=14)
    ax4.set_ylabel("ASMR (Male)", fontsize=14)
    ax1.set_xlabel(f"{axis_label} (2019)", fontsize=14)
    ax2.set_xlabel(f"{axis_label} (2019)", fontsize=14)
    ax3.set_xlabel(f"{axis_label} (2024)", fontsize=14)
    ax4.set_xlabel(f"{axis_label} (2024)", fontsize=14)

    legend_elements = [
        Patch(facecolor=color_mapping["Con"], edgecolor=(0, 0, 0, 1), label="Conservative"),
        Patch(facecolor=color_mapping["Lab"], edgecolor=(0, 0, 0, 1), label="Labour"),
        Patch(facecolor=color_mapping["Other"], edgecolor=(0, 0, 0, 1), label="Other"),
    ]
    ax1.legend(
        handles=legend_elements,
        loc="upper left" if party_column == "Lab PC" else "upper right",
        frameon=True,
        fontsize=10,
        framealpha=1,
        facecolor="w",
        edgecolor=(0, 0, 0, 1),
        ncols=1,
    )

    for ax, title in zip(axes, ["a.", "b.", "c.", "d."]):
        y_min, y_max = ax.get_ylim()
        ax.set_ylim(y_min - 0.05 * (y_max - y_min), y_max)
        ax.grid(which="both", linestyle="--", alpha=0.3)
        ax.set_title(title, loc="left", fontsize=19, fontweight="bold", y=1.0)

    annotate_pos = "lower right" if party_column == "Lab PC" else "lower left"
    correlation_specs = [
        (ax1, df_2019, "ASMR_f", 2019, "F", 4),
        (ax2, df_2019, "ASMR_m", 2019, "M", 3),
        (ax3, df_2024, "ASMR_f", 2024, "F", 4),
        (ax4, df_2024, "ASMR_m", 2024, "M", 3),
    ]
    for ax, df, asmr_column, year, sex, decimals in correlation_specs:
        pair_df = df[[party_column, asmr_column]].dropna()
        pearson_r, pearson_p = pearsonr(pair_df[party_column], pair_df[asmr_column])
        spearman_rho, spearman_p = spearmanr(pair_df[party_column], pair_df[asmr_column])
        pearson_r = f"{pearson_r:.{decimals}f}"
        spearman_rho = f"{spearman_rho:.{decimals}f}"
        annotation_text = (
            r"Spearman $\rho$ = " + spearman_rho + "\n"
            r"Pearson $r$ = " + pearson_r
        )
        at = AnchoredText(annotation_text, prop=dict(size=9), frameon=True, loc=annotate_pos)
        at.patch.set_boxstyle("round,pad=0.,rounding_size=0.2")
        ax.add_artist(at)
        print(
            f"{year}: {party_label} vote share vs ASMR ({sex}) "
            f"Spearman rho: {spearman_rho}, p-value {spearman_p}; "
            f"Pearson r: {pearson_r}, p-value {pearson_p}"
        )

    if annotate_leaders:
        _annotate_scatter_leaders(ax1, ax2, ax3, ax4, df_2019, df_2024)

    sns.despine()
    _save_figure(fig, f"{party_slug}_asmr_scatter")
    plt.close(fig)
    return fig


def _annotate_scatter_leaders(ax1, ax2, ax3, ax4, df_2019, df_2024):
    corbyn = df_2019[df_2019["Constituency name"].str.contains("Islington", regex=False)]
    johnson = df_2019[df_2019["Constituency name"].str.contains("Uxbridge", regex=False)]
    starmer = df_2024[df_2024["Constituency name"].str.contains("Pancras", regex=False)]
    sunak = df_2024[df_2024["Constituency name"].str.contains("Richmond", regex=False)]

    leader_specs = [
        (ax1, johnson, "Uxbridge and\nSouth Ruislip", "ASMR_f", (-0.25, 300), "arc3,rad=.45"),
        (ax1, corbyn, "Islington North", "ASMR_f", (0.15, 500), "arc3,rad=-.45"),
        (ax2, johnson, "Uxbridge and\nSouth Ruislip", "ASMR_m", (-0.2, 340), "arc3,rad=.45"),
        (ax2, corbyn, "Islington North", "ASMR_m", (0.125, 500), "arc3,rad=-.45"),
        (ax3, starmer, "Holborn\nand\nSt Pancras", "ASMR_f", (0.19, 60), "arc3,rad=-.45"),
        (ax3, sunak, "Richmond and\nNorthallerton", "ASMR_f", (-0.1, 400), "arc3,rad=.45"),
        (ax4, starmer, "Holborn\nand\nSt Pancras", "ASMR_m", (0.2, 315), "arc3,rad=-.45"),
        (ax4, sunak, "Richmond and\nNorthallerton", "ASMR_m", (-0.1, 600), "arc3,rad=.45"),
    ]
    for ax, df, label, asmr_column, offset, connectionstyle in leader_specs:
        if df.empty:
            continue
        x = df["Lab PC"].iloc[0]
        y = df[asmr_column].iloc[0]
        ax.annotate(
            label,
            xy=(x, y),
            xytext=(x + offset[0], y + offset[1]),
            ha="center",
            va="bottom",
            arrowprops=dict(
                arrowstyle="->",
                connectionstyle=connectionstyle,
                color="black",
                mutation_scale=30,
                lw=1.5,
            ),
        )


def minimum_bounding_circle(polygon):
    points = list(polygon.exterior.coords)
    multi_point = MultiPoint(points)
    center = multi_point.centroid
    radius = 0

    for point in multi_point.geoms:
        distance = center.distance(point)
        if distance > radius:
            radius = distance

    return center, radius


class BivariateChoroplethPlotter:
    def __init__(self, x_edges, y_edges):
        if len(x_edges) != len(y_edges):
            raise ValueError("x_edges and y_edges must have the same length")
        self.x_edges = list(x_edges)
        self.y_edges = list(y_edges)
        self.num_groups = len(self.x_edges) - 1
        self.alpha_value = 0.85
        self.light_gray, self.green, self.blue, self.dark_blue = self.define_corner_colors()
        self.color_list_hex = self.create_color_list()

    def hex_to_rgb_color(self, hex_code):
        return [int(hex_code[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]

    def define_corner_colors(self):
        return (
            self.hex_to_rgb_color("#e8e8e8"),
            self.hex_to_rgb_color("#6c83b5"),
            self.hex_to_rgb_color("#73ae80"),
            self.hex_to_rgb_color("#2a5a5b"),
        )

    def create_color_list(self):
        light_gray_to_green = []
        blue_to_dark_blue = []
        color_list = []

        for i in range(self.num_groups):
            light_gray_to_green.append(
                [
                    self.light_gray[j]
                    + (self.green[j] - self.light_gray[j]) * i / (self.num_groups - 1)
                    for j in range(3)
                ]
            )
            blue_to_dark_blue.append(
                [
                    self.blue[j]
                    + (self.dark_blue[j] - self.blue[j]) * i / (self.num_groups - 1)
                    for j in range(3)
                ]
            )

        for i in range(self.num_groups):
            for j in range(self.num_groups):
                color_list.append(
                    [
                        light_gray_to_green[i][k]
                        + (blue_to_dark_blue[i][k] - light_gray_to_green[i][k])
                        * j
                        / (self.num_groups - 1)
                        for k in range(3)
                    ]
                )

        return ["#%02x%02x%02x" % tuple(int(c * 255) for c in color) for color in color_list]

    def get_bin_index(self, value, edges):
        if value is None or value != value or value < 0:
            return None
        for i, upper_bound in enumerate(edges[1:]):
            if value <= upper_bound:
                return i
        return self.num_groups - 1

    def get_bivariate_color(self, p1, p2):
        i = self.get_bin_index(p1, self.x_edges)
        j = self.get_bin_index(p2, self.y_edges)
        if i is None or j is None:
            return "#cccccc"
        return self.color_list_hex[i * self.num_groups + j]

    def plot_bivariate_choropleth(self, geometry, ax=None):
        if ax is None:
            fig, ax = plt.subplots(1, 1, figsize=(12, 12))
        else:
            fig = ax.get_figure()

        geometry["color_bivariate"] = [
            self.get_bivariate_color(p1, p2)
            for p1, p2 in zip(geometry["column1"].values, geometry["column2"].values)
        ]
        geometry.plot(
            ax=ax,
            color=geometry["color_bivariate"],
            alpha=self.alpha_value,
            legend=False,
            linewidth=0.00,
        )
        ax.set_xticks([])
        ax.set_yticks([])
        return fig, ax

    def plot_inset_legend(self, ax, yaxis_label, xaxis_label):
        ax_inset = ax.inset_axes([0.0125, 0.275, 0.3, 0.3])
        ax_inset.set_aspect("equal", adjustable="box")
        x_ticks = [self.format_tick_label(value, significant_digits=1) for value in self.x_edges]
        y_ticks = [self.format_tick_label(value) for value in self.y_edges]

        for i in range(self.num_groups):
            for j in range(self.num_groups):
                rect = plt.Rectangle(
                    (i, j),
                    1,
                    1,
                    edgecolor="k",
                    linewidth=0.5,
                    facecolor=self.color_list_hex[i * self.num_groups + j],
                    alpha=self.alpha_value,
                )
                ax_inset.add_patch(rect)

        ax_inset.set_xlim([0, self.num_groups])
        ax_inset.set_ylim([0, self.num_groups])
        ax_inset.set_xticks(list(range(self.num_groups + 1)), x_ticks, fontsize=15)
        ax_inset.set_xlabel(xaxis_label, fontsize=16)
        ax_inset.set_yticks(list(range(self.num_groups + 1)), y_ticks, fontsize=15)
        ax_inset.set_ylabel(yaxis_label, fontsize=16)

    def format_tick_label(self, value, significant_digits=None):
        if value != value:
            return ""
        if significant_digits is not None:
            return f"{value:.{significant_digits}g}"
        if abs(value) < 1:
            return f"{value:.2f}"
        return f"{value:.0f}"


def _quantile_edges(*columns, num_groups=5):
    values = pd.concat(columns, ignore_index=True).dropna()
    return values.quantile(np.linspace(0, 1, num_groups + 1)).to_numpy()


def _set_map_axis(ax, title):
    ax.set_xlim(125000, 660000)
    ax.set_ylim(10000, 675000)
    ax.set_title(title, fontsize=35, fontweight="bold", loc="left", y=0.965, x=0)
    sns.despine(ax=ax, left=True, right=True, top=True, bottom=True)
    ax.annotate(
        "N",
        xy=(0.8, 0.95),
        xytext=(0.8, 0.95 - 0.125),
        arrowprops=dict(facecolor="black", width=2.5, headwidth=15),
        ha="center",
        va="center",
        fontsize=20,
        xycoords=ax.transAxes,
    )


def _circle_and_label(ax, row, label, xytext, radius_scale, connectionstyle):
    if row.empty:
        return
    convex_hull = row["geometry"].convex_hull
    center, radius = minimum_bounding_circle(convex_hull.iloc[0])
    circle = Point(center).buffer(radius * radius_scale)
    gpd.GeoSeries([circle]).plot(
        color=(1, 1, 1, 0.2),
        ax=ax,
        edgecolor=(0, 0, 0, 1),
        linewidth=1.5,
    )
    ax.annotate(
        label,
        xy=(center.x, center.y),
        xytext=xytext(center),
        ha="center",
        va="center",
        fontsize=16,
        arrowprops=dict(
            arrowstyle="->",
            connectionstyle=connectionstyle,
            color="black",
            mutation_scale=30,
            lw=1.5,
        ),
    )


def _annotate_map_leaders(axs, df_gpd_2019, df_gpd_2024):
    starmer = df_gpd_2024[df_gpd_2024["PCON24NM"].str.contains("Pancras", regex=False, na=False)]
    sunak = df_gpd_2024[
        df_gpd_2024["PCON24NM"].str.contains("Richmond and Northallerton", regex=False, na=False)
    ]
    speaker_2024 = df_gpd_2024[df_gpd_2024["PCON24NM"].str.contains("Chorley", regex=False, na=False)]
    corbyn = df_gpd_2019[
        df_gpd_2019["Constituency name"].str.contains("Islington North", regex=False, na=False)
    ]
    johnson = df_gpd_2019[
        df_gpd_2019["Constituency name"].str.contains("Uxbridge", regex=False, na=False)
    ]
    speaker_2019 = df_gpd_2019[
        df_gpd_2019["Constituency name"].str.contains("Chorley", regex=False, na=False)
    ]

    for ax in [axs[1, 0], axs[1, 1]]:
        _circle_and_label(
            ax,
            sunak,
            "Richmond and\nNorthallerton\n(Rishi Sunak)",
            lambda center: (center.x - 200000, center.y),
            1,
            "arc3,rad=-.30",
        )
        _circle_and_label(
            ax,
            starmer,
            "Holborn and\nSt Pancras\n(Keir Starmer)",
            lambda center: (center.x, center.y - 140000),
            1.3,
            "arc3,rad=-.45",
        )
        _circle_and_label(
            ax,
            speaker_2024,
            "Chorley\n(Speaker)",
            lambda center: (center.x - 135000, center.y),
            1.2,
            "arc3,rad=.45",
        )

    for ax in [axs[0, 0], axs[0, 1]]:
        _circle_and_label(
            ax,
            johnson,
            "Uxbridge and\nSouth Ruislip\n(Boris Johnson)",
            lambda center: (center.x + 120000, center.y + 225000),
            1,
            "arc3,rad=.35",
        )
        _circle_and_label(
            ax,
            corbyn,
            "Islington North\n(Jeremy Corbyn)",
            lambda center: (center.x, center.y - 140000),
            1.3,
            "arc3,rad=.45",
        )
        _circle_and_label(
            ax,
            speaker_2019,
            "Chorley\n(Speaker)",
            lambda center: (center.x - 135000, center.y),
            1.2,
            "arc3,rad=-.45",
        )


def _write_derived(geodata, party_code, measure, year):
    _ensure_output_dirs()
    _, _, _, party_slug = _party_metadata_from_code_or_column(party_code)
    geodata.to_csv(DERIVED_DIR / f"{party_slug}_{measure}_ranked_data_{year}.csv")


def plot_bivariate_choropleth_map_census(df_gpd_2019, df_gpd_2024, party_list):
    _ensure_output_dirs()
    df_gpd_2019 = df_gpd_2019[df_gpd_2019["Country name"] == "England"].copy()
    df_gpd_2024 = df_gpd_2024[df_gpd_2024["Country name"] == "England"].copy()
    print("Length of the 2019 dataset going into this: ", len(df_gpd_2019))
    print("Length of the 2024 dataset going into this: ", len(df_gpd_2024))

    party_code, fallback_label = party_list
    party_code, _, axis_label, party_slug = _party_metadata_from_code_or_column(
        party_code,
        fallback_label,
    )
    party_pc_column = f"{party_code} PC"
    keep_columns = [party_pc_column, "ProportionBadHealth", "ProportionDisabled"]
    df_gpd_2019 = df_gpd_2019.dropna(subset=keep_columns).copy()
    df_gpd_2024 = df_gpd_2024.dropna(subset=keep_columns).copy()

    vote_edges = _quantile_edges(df_gpd_2019[party_pc_column], df_gpd_2024[party_pc_column])
    health_edges = _quantile_edges(df_gpd_2019["ProportionBadHealth"], df_gpd_2024["ProportionBadHealth"])
    disability_edges = _quantile_edges(
        df_gpd_2019["ProportionDisabled"],
        df_gpd_2024["ProportionDisabled"],
    )
    plotter_health = BivariateChoroplethPlotter(vote_edges, health_edges)
    plotter_disability = BivariateChoroplethPlotter(vote_edges, disability_edges)
    fig, axs = plt.subplots(2, 2, figsize=(20, 24))

    df_gpd_2019["column1"] = df_gpd_2019[party_pc_column]
    df_gpd_2019["column2"] = df_gpd_2019["ProportionBadHealth"]
    df_gpd_2019["column3"] = df_gpd_2019["ProportionDisabled"]
    df_gpd_2024["column1"] = df_gpd_2024[party_pc_column]
    df_gpd_2024["column2"] = df_gpd_2024["ProportionBadHealth"]
    df_gpd_2024["column3"] = df_gpd_2024["ProportionDisabled"]

    _write_derived(df_gpd_2019, party_code, "census", 2019)
    _write_derived(df_gpd_2024, party_code, "census", 2024)

    plotter_health.plot_bivariate_choropleth(df_gpd_2019, ax=axs[0, 0])
    plotter_health.plot_inset_legend(
        axs[0, 0],
        "Proportion Not\nGood Health (2019)",
        f"{axis_label}\n(2019)",
    )
    _set_map_axis(axs[0, 0], "a.")

    df_gpd_2019["column2"] = df_gpd_2019["column3"]
    plotter_disability.plot_bivariate_choropleth(df_gpd_2019, ax=axs[0, 1])
    plotter_disability.plot_inset_legend(
        axs[0, 1],
        "Proportion\nDisabled (2019)",
        f"{axis_label}\n(2019)",
    )
    _set_map_axis(axs[0, 1], "b.")

    plotter_health.plot_bivariate_choropleth(df_gpd_2024, ax=axs[1, 0])
    plotter_health.plot_inset_legend(
        axs[1, 0],
        "Proportion Not\nGood Health (2024)",
        f"{axis_label}\n(2024)",
    )
    _set_map_axis(axs[1, 0], "c.")

    df_gpd_2024["column2"] = df_gpd_2024["column3"]
    plotter_disability.plot_bivariate_choropleth(df_gpd_2024, ax=axs[1, 1])
    plotter_disability.plot_inset_legend(
        axs[1, 1],
        "Proportion\nDisabled (2024)",
        f"{axis_label}\n(2024)",
    )
    _set_map_axis(axs[1, 1], "d.")

    _annotate_map_leaders(axs, df_gpd_2019, df_gpd_2024)
    plt.subplots_adjust(wspace=0.2)
    plt.subplots_adjust(hspace=0.0)
    _save_figure(fig, f"{party_slug}_census_health_disability_bivariate_choropleth")
    plt.close(fig)
    return fig


def plot_bivariate_choropleth_map_asmr(df_gpd_2019, df_gpd_2024, party_list):
    _ensure_output_dirs()
    df_gpd_2019 = df_gpd_2019[df_gpd_2019["Country name"] == "England"].copy()
    df_gpd_2024 = df_gpd_2024[df_gpd_2024["Country name"] == "England"].copy()
    print("Length of the 2019 dataset going into this: ", len(df_gpd_2019))
    print("Length of the 2024 dataset going into this: ", len(df_gpd_2024))

    party_code, fallback_label = party_list
    party_code, _, axis_label, party_slug = _party_metadata_from_code_or_column(
        party_code,
        fallback_label,
    )
    party_pc_column = f"{party_code} PC"
    vote_edges = _quantile_edges(df_gpd_2019[party_pc_column], df_gpd_2024[party_pc_column])
    asmr_f_edges = _quantile_edges(df_gpd_2019["ASMR_f"], df_gpd_2024["ASMR_f"])
    asmr_m_edges = _quantile_edges(df_gpd_2019["ASMR_m"], df_gpd_2024["ASMR_m"])
    plotter_f = BivariateChoroplethPlotter(vote_edges, asmr_f_edges)
    plotter_m = BivariateChoroplethPlotter(vote_edges, asmr_m_edges)
    fig, axs = plt.subplots(2, 2, figsize=(20, 24))

    df_gpd_2019["column1"] = df_gpd_2019[party_pc_column]
    df_gpd_2019["column2"] = df_gpd_2019["ASMR_f"]
    df_gpd_2019["column3"] = df_gpd_2019["ASMR_m"]
    df_gpd_2024["column1"] = df_gpd_2024[party_pc_column]
    df_gpd_2024["column2"] = df_gpd_2024["ASMR_f"]
    df_gpd_2024["column3"] = df_gpd_2024["ASMR_m"]

    _write_derived(df_gpd_2019, party_code, "asmr", 2019)
    _write_derived(df_gpd_2024, party_code, "asmr", 2024)

    plotter_f.plot_bivariate_choropleth(df_gpd_2019, ax=axs[0, 0])
    plotter_f.plot_inset_legend(
        axs[0, 0],
        "ASMR\n(Female, 2019)",
        f"{axis_label}\n(2019)",
    )
    _set_map_axis(axs[0, 0], "a.")

    df_gpd_2019["column2"] = df_gpd_2019["column3"]
    plotter_m.plot_bivariate_choropleth(df_gpd_2019, ax=axs[0, 1])
    plotter_m.plot_inset_legend(
        axs[0, 1],
        "ASMR\n(Male, 2019)",
        f"{axis_label}\n(2019)",
    )
    _set_map_axis(axs[0, 1], "b.")

    plotter_f.plot_bivariate_choropleth(df_gpd_2024, ax=axs[1, 0])
    plotter_f.plot_inset_legend(
        axs[1, 0],
        "ASMR\n(Female, 2024)",
        f"{axis_label}\n(2024)",
    )
    _set_map_axis(axs[1, 0], "c.")

    df_gpd_2024["column2"] = df_gpd_2024["column3"]
    plotter_m.plot_bivariate_choropleth(df_gpd_2024, ax=axs[1, 1])
    plotter_m.plot_inset_legend(
        axs[1, 1],
        "ASMR\n(Male, 2024)",
        f"{axis_label}\n(2024)",
    )
    _set_map_axis(axs[1, 1], "d.")

    _annotate_map_leaders(axs, df_gpd_2019, df_gpd_2024)
    plt.subplots_adjust(wspace=0.2)
    plt.subplots_adjust(hspace=0.0)
    _save_figure(fig, f"{party_slug}_asmr_bivariate_choropleth")
    plt.close(fig)
    return fig


def make_summary_tables(df_1, df_2, year):
    if year == "2019":
        party_share = ["Con PC", "Lab PC", "Lib PC", "Brx PC", "Vote PC"]
    elif year == "2024":
        party_share = ["Con PC", "Lab PC", "Lib PC", "RUK PC", "Vote PC"]
    else:
        raise ValueError("year must be 2019 or 2024")

    crosstab_var = [
        "ASMR_f",
        "ASMR_m",
        "ProportionBadHealth",
        "ProportionDisabled",
        "ProportionProvidesAnyUnpaidCare",
        "HealthDeprivationAndDisabilityRank",
    ]
    statistic_functions = [("Spearman", spearmanr), ("Pearson", pearsonr)]
    df = df_2.copy()

    coefficient_tables = []
    p_value_tables = []
    for statistic_name, statistic_function in statistic_functions:
        table_r = pd.DataFrame(columns=["Year", "N"] + party_share, index=crosstab_var)
        table_p = pd.DataFrame(columns=["Year", "N"] + party_share, index=crosstab_var)

        for index in crosstab_var:
            table_r.at[index, "Year"] = year
            table_p.at[index, "Year"] = year
            table_r.at[index, "N"] = df[index].notnull().sum()
            table_p.at[index, "N"] = df[index].notnull().sum()

            for col in party_share:
                pair_df = df[[col, index]].dropna()
                r, p = statistic_function(pair_df[col], pair_df[index])
                table_r.loc[index, col] = r
                table_p.loc[index, col] = p

        coefficient_tables.append(table_r)
        p_value_tables.append(table_p)

    table_rho = pd.concat(
        coefficient_tables,
        keys=[name for name, _ in statistic_functions],
        names=["Statistic", "Variable"],
    ).reset_index()
    table_p = pd.concat(
        p_value_tables,
        keys=[name for name, _ in statistic_functions],
        names=["Statistic", "Variable"],
    ).reset_index()
    return table_rho, table_p


def make_sii():
    df = pd.read_excel(RAW_DIR / "life_expectancy" / "trends_in_sii.xlsx")
    df["timeperiod"] = df["timeperiod"].str.replace(" - ", "-")
    return df.set_index("timeperiod")


def make_hid():
    df_hid = pd.read_csv(
        RAW_DIR / "life_expectancy" / "HID_data_Life expectancy and mortality.csv"
    )
    df_hid["Time period"] = df_hid["Time period"].str.replace(" - ", "-")
    return df_hid.set_index("Time period")


def plot_over_time(df_sii, df_hid):
    _ensure_output_dirs()
    colors = ["#E4003B", "#0087DC", "#4a6741"]
    fig = plt.figure(figsize=(11, 5.5))
    gs = grid_spec.GridSpec(2, 2, width_ratios=[1, 1])
    ax1 = plt.subplot(gs[:, 0])
    ax2 = plt.subplot(gs[0, 1])
    ax2_twinx = ax2.twinx()
    ax3 = plt.subplot(gs[1, 1])
    ax3_twinx = ax3.twinx()

    females = df_sii[df_sii["sex"] == "Females"]
    males = df_sii[df_sii["sex"] == "Males"]
    first_9_indices = females.index[:9]
    remaining_indices = females.index[9:]

    for sex_df, marker in [(females, "s"), (males, "o")]:
        for indices, color in [(first_9_indices, colors[0]), (remaining_indices, colors[1])]:
            ax1.errorbar(
                indices,
                sex_df.loc[indices, "value"],
                yerr=[
                    sex_df.loc[indices, "value"] - sex_df.loc[indices, "lower95ci"],
                    sex_df.loc[indices, "upper95ci"] - sex_df.loc[indices, "value"],
                ],
                fmt=marker,
                markersize=7,
                color=color,
                markeredgecolor="k",
                ecolor="k",
                linewidth=0.5,
                capsize=6,
            )

    legend_elements1 = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=colors[0], markeredgecolor="k", markersize=6, label="Male (Pre-2010)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=colors[1], markeredgecolor="k", markersize=6, label="Male (Post-2010)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=colors[0], markeredgecolor="k", markersize=6, label="Female (Pre-2010)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=colors[1], markeredgecolor="k", markersize=6, label="Female (Post-2010)"),
    ]
    ax1.legend(
        handles=legend_elements1,
        loc="lower right",
        frameon=True,
        fontsize=8.5,
        framealpha=1,
        facecolor="w",
        edgecolor=(0, 0, 0, 1),
        ncols=1,
    )
    ax1.xaxis.set_major_locator(ticker.MaxNLocator(nbins=7))

    hid_specs = [
        (ax2_twinx, "Healthy life expectancy at birth - Male", "10 = least deprived", colors[0], "o"),
        (ax2_twinx, "Healthy life expectancy at birth - Male", "5", colors[1], "d"),
        (ax2_twinx, "Healthy life expectancy at birth - Male", "01 = most deprived", colors[2], "s"),
        (ax3_twinx, "Healthy life expectancy at birth - Female", "10 = least deprived", colors[0], "o"),
        (ax3_twinx, "Healthy life expectancy at birth - Female", "5", colors[1], "d"),
        (ax3_twinx, "Healthy life expectancy at birth - Female", "01 = most deprived", colors[2], "s"),
    ]
    for ax, indicator, category, markerfacecolor, marker in hid_specs:
        df_hid[(df_hid["Indicator"] == indicator) & (df_hid["Category"] == category)][
            ["Value"]
        ].plot(
            ax=ax,
            linewidth=0.5,
            markerfacecolor=markerfacecolor,
            color="k",
            marker=marker,
            markeredgecolor="k",
            legend=False,
        )

    for grid_ax in [ax2_twinx, ax3_twinx]:
        grid_ax.grid(which="major", linestyle="--", axis="y", alpha=0.3)
    for grid_ax in [ax2, ax3]:
        grid_ax.grid(which="major", linestyle="--", axis="x", alpha=0.3)
    ax1.grid(which="major", linestyle="--", axis="both", alpha=0.3)

    ax1.set_title("a.", fontsize=20, loc="left")
    ax2_twinx.set_title("b.", fontsize=21, loc="left")
    ax3_twinx.set_title("c.", fontsize=21, loc="left")
    ax1.set_ylabel("Slope Index of Inequality\n(Life Expectancy at Birth Differential)", fontsize=13)
    ax2_twinx.set_ylabel("Male Healthy LE\n(at Birth)", fontsize=13)
    ax3_twinx.set_ylabel("Female Healthy LE\n(at Birth)", fontsize=13)

    for ax in [ax1, ax2, ax3]:
        ax.tick_params(axis="x", rotation=0, labelsize=9)

    ax2_twinx.set_ylim(43.5, 72.5)
    ax3_twinx.set_ylim(43.5, 72.5)
    ax2.set_xticklabels([])
    ax2.set_yticklabels([])
    ax2.set_yticks([])
    ax3.set_yticklabels([])
    ax3.set_yticks([])

    sns.despine(ax=ax1)
    sns.despine(ax=ax2, left=True, right=False)
    sns.despine(ax=ax2_twinx, left=True)
    sns.despine(ax=ax3, left=True, right=False)
    sns.despine(ax=ax3_twinx, left=True)

    legend_elements3 = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=colors[0], markeredgecolor="k", markersize=6, label="Least Deprived"),
        Line2D([0], [0], marker="d", color="w", markerfacecolor=colors[1], markeredgecolor="k", markersize=6, label="5th Decile"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=colors[2], markeredgecolor="k", markersize=6, label="Most Deprived"),
    ]
    ax3_twinx.legend(
        handles=legend_elements3,
        loc="lower center",
        frameon=True,
        fontsize=9,
        framealpha=1,
        facecolor=(1, 1, 1, 1),
        edgecolor=(0, 0, 0, 1),
        ncols=3,
    )

    ax1.axvline(x=9, color="k", linestyle="--")
    ax1.annotate(
        "General Election\n(2010)",
        xy=(9.15, 7.75),
        xytext=(2.5, 7.75),
        ha="center",
        va="center",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", edgecolor="black", facecolor="w"),
        arrowprops=dict(
            arrowstyle="->",
            connectionstyle="arc3,rad=0",
            color="black",
            mutation_scale=20,
            lw=1,
        ),
    )

    fig.tight_layout()
    _save_figure(fig, "health_inequality_over_time")
    plt.close(fig)
    return fig


def make_temporal_printouts(df_sii, df_hid):
    df_sii_f = df_sii[df_sii["sex"] == "Females"]
    print(f"In 2001-2003, the SII for females was: {df_sii_f.loc['2001-03', 'value']}")
    print(f"In 2018-2020, the SII for females was: {df_sii_f.loc['2018-20', 'value']}")

    df_sii_m = df_sii[df_sii["sex"] == "Males"]
    print(f"In 2001-2003, the SII for males was: {df_sii_m.loc['2001-03', 'value']}")
    print(f"In 2018-2020, the SII for males was: {df_sii_m.loc['2018-20', 'value']}")

    df_hid_m_10 = df_hid[
        (df_hid["Indicator"] == "Healthy life expectancy at birth - Male")
        & (df_hid["Category"] == "10 = least deprived")
    ]
    df_hid_m_1 = df_hid[
        (df_hid["Indicator"] == "Healthy life expectancy at birth - Male")
        & (df_hid["Category"] == "01 = most deprived")
    ]
    print(f"In 2011-2013, Male Healthy LE for 1st decile was: {df_hid_m_1[['Value']].loc['2011-13', 'Value']}")
    print(f"In 2011-2013, Male Healthy LE for 10th decile was: {df_hid_m_10[['Value']].loc['2011-13', 'Value']}")
    print(f"In 2018-2020, Male Healthy LE for 1st decile was: {df_hid_m_1[['Value']].loc['2018-20', 'Value']}")
    print(f"In 2018-2020, Male Healthy LE for 10th decile was: {df_hid_m_10[['Value']].loc['2018-20', 'Value']}")

    df_hid_f_10 = df_hid[
        (df_hid["Indicator"] == "Healthy life expectancy at birth - Female")
        & (df_hid["Category"] == "10 = least deprived")
    ]
    df_hid_f_1 = df_hid[
        (df_hid["Indicator"] == "Healthy life expectancy at birth - Female")
        & (df_hid["Category"] == "01 = most deprived")
    ]
    print(f"In 2011-2013, Female Healthy LE for 1st decile was: {df_hid_f_1[['Value']].loc['2011-13', 'Value']}")
    print(f"In 2011-2013, Female Healthy LE for 10th decile was: {df_hid_f_10[['Value']].loc['2011-13', 'Value']}")
    print(f"In 2018-2020, Female Healthy LE for 1st decile was: {df_hid_f_1[['Value']].loc['2018-20', 'Value']}")
    print(f"In 2018-2020, Female Healthy LE for 10th decile was: {df_hid_f_10[['Value']].loc['2018-20', 'Value']}")
