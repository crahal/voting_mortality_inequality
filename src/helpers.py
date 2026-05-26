import json
import urllib.parse
import urllib.request
from pathlib import Path

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

mpl.rcParams["font.family"] = "Helvetica"

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
    fig.savefig(OUTPUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(OUTPUT_DIR / f"{stem}.svg", bbox_inches="tight")


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
        ax.grid(which="both", linestyle="--", alpha=0.3)
        ax.set_title(title, loc="left", fontsize=20, y=1.0)

    annotate_pos = "lower right" if party_column == "Lab PC" else "lower left"
    correlation_specs = [
        (ax1, df_2019, "ASMR_f", 2019, "F", 4),
        (ax2, df_2019, "ASMR_m", 2019, "M", 3),
        (ax3, df_2024, "ASMR_f", 2024, "F", 4),
        (ax4, df_2024, "ASMR_m", 2024, "M", 3),
    ]
    for ax, df, asmr_column, year, sex, decimals in correlation_specs:
        r, p = pearsonr(df[party_column], df[asmr_column])
        r = np.round(r, decimals)
        at = AnchoredText(r"$r$ = " + str(r), prop=dict(size=13), frameon=True, loc=annotate_pos)
        at.patch.set_boxstyle("round,pad=0.,rounding_size=0.2")
        ax.add_artist(at)
        print(
            f"{year}: {party_label} vote share vs ASMR ({sex}) "
            f"pearsons r: {r}, p-value {p}"
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
        (ax1, johnson, "Uxbridge and\nSouth Ruislip", "ASMR_f", (-0.2, 150), "arc3,rad=.45"),
        (ax1, corbyn, "Islington North", "ASMR_f", (0, 255), "arc3,rad=-.45"),
        (ax2, johnson, "Uxbridge and\nSouth Ruislip", "ASMR_m", (-0.175, 340), "arc3,rad=.45"),
        (ax2, corbyn, "Islington North", "ASMR_m", (0, 320), "arc3,rad=-.45"),
        (ax3, starmer, "Holborn and\nSt Pancras", "ASMR_f", (0.15, 225), "arc3,rad=-.45"),
        (ax3, sunak, "Richmond and\nNorthallerton", "ASMR_f", (-0.05, 260), "arc3,rad=.45"),
        (ax4, starmer, "Holborn and\nSt Pancras", "ASMR_m", (0.2, 315), "arc3,rad=-.45"),
        (ax4, sunak, "Richmond and\nNorthallerton", "ASMR_m", (-0.05, 300), "arc3,rad=.45"),
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
        x_ticks = [self.format_tick_label(value) for value in self.x_edges]
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

    def format_tick_label(self, value):
        if value != value:
            return ""
        if abs(value) < 1:
            return f"{value:.2f}"
        return f"{value:.0f}"


def _quantile_edges(*columns, num_groups=5):
    values = pd.concat(columns, ignore_index=True).dropna()
    return values.quantile(np.linspace(0, 1, num_groups + 1)).to_numpy()


def _set_map_axis(ax, title):
    ax.set_xlim(125000, 660000)
    ax.set_ylim(10000, 675000)
    ax.set_title(title, fontsize=35, loc="left", y=0.965, x=0)
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

    for ax in [axs[0, 1], axs[1, 1]]:
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

    for ax in [axs[0, 0], axs[1, 0]]:
        _circle_and_label(
            ax,
            johnson,
            "Uxbridge and\nSouth Ruislip\n(Boris Johnson)",
            lambda center: (center.x + 120000, center.y + 200000),
            1,
            "arc3,rad=-.225",
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
    plotter_disability.plot_bivariate_choropleth(df_gpd_2019, ax=axs[1, 0])
    plotter_disability.plot_inset_legend(
        axs[1, 0],
        "Proportion\nDisabled (2019)",
        f"{axis_label}\n(2019)",
    )
    _set_map_axis(axs[1, 0], "c.")

    plotter_health.plot_bivariate_choropleth(df_gpd_2024, ax=axs[0, 1])
    plotter_health.plot_inset_legend(
        axs[0, 1],
        "Proportion Not\nGood Health (2024)",
        f"{axis_label}\n(2024)",
    )
    _set_map_axis(axs[0, 1], "b.")

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
    plotter_m.plot_bivariate_choropleth(df_gpd_2019, ax=axs[1, 0])
    plotter_m.plot_inset_legend(
        axs[1, 0],
        "ASMR\n(Male, 2019)",
        f"{axis_label}\n(2019)",
    )
    _set_map_axis(axs[1, 0], "c.")

    plotter_f.plot_bivariate_choropleth(df_gpd_2024, ax=axs[0, 1])
    plotter_f.plot_inset_legend(
        axs[0, 1],
        "ASMR\n(Female, 2024)",
        f"{axis_label}\n(2024)",
    )
    _set_map_axis(axs[0, 1], "b.")

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
