# Data Sources and Provenance

[Project overview](../README.md) | [Reproduction guide](reproducibility.md)

The analysis covers English parliamentary constituencies. Source workbooks can
have broader geographic coverage; the pipeline applies its England filters
explicitly. Dataset years, election years and boundary vintages are not
interchangeable.

## Main Sources

| Source family | Dataset and role |
|---|---|
| Election results | House of Commons Library [2019 results](https://commonslibrary.parliament.uk/research-briefings/cbp-8749/) and [2024 results](https://commonslibrary.parliament.uk/research-briefings/cbp-10009/). Party vote shares use valid votes; turnout uses valid plus invalid votes divided by the electorate. |
| Mortality | ONS [release 3175](https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/deaths/adhocs/3175numbersandagestandardisedmortalityratesofdeathspopulationcountsbysexandparliamentaryconstituencyenglandandwalesdeathsregisteredin2019and2024): sex-specific ASMR, deaths and population counts for 2019 and 2024. ONS [release 1961](https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/deaths/adhocs/1961numbersandagestandardisedmortalityratesforprematuredeathsbyparliamentaryconstituencyandsexin2021): a separate 2021 premature-mortality outcome. |
| Census | ONS Census 2021 general health, disability and unpaid care, retrieved through custom filter outputs. [General-health dataset metadata](https://api.beta.ons.gov.uk/v1/datasets/RM014/editions/2021/versions/1). The exact filters, geography dimensions and download recipes are in the manifest. |
| Deprivation | [English Indices of Deprivation 2019](https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019) LSOA scores, ONS geography lookups, and the [2025 constituency workbook](https://commonslibrary.parliament.uk/research-briefings/cbp-10526/) for the 2024-election comparison. |

The authoritative file manifest is `RAW_DATA_SOURCES` together with
`RAW_DATA_SOURCE_EXTRA_FILES` in [helpers.py](../src/helpers.py). It records exact
paths, byte counts, SHA-256 values and retrieval recipes. Section 1 of the
[analysis notebook](../src/analysis.ipynb) contains clickable source and data links.
Print the complete manifest without downloading anything:

```bash
python scripts/manage_data.py sources
```

## Geography and Deprivation

The 2019 election uses the pre-2024 constituency geography; the 2024 election
uses the revised boundaries. The pipeline uses the named 2019 generalised,
clipped boundary files and 2024 full-resolution, clipped boundary files, with
the existing 400-metre topology-preserving simplification for maps.

For 2019 deprivation, the pipeline joins 2011 Output Areas to both 2011 LSOAs
and constituencies. Each LSOA is assigned to the constituency containing the
largest number of its Output Areas; ties are resolved by constituency code.
It then calculates a population-weighted mean Health Deprivation and Disability
score using the source's mid-2015 population denominator, excluding prisoners,
and ranks constituencies with the highest score ranked 1. This is a constructed
constituency measure, not a direct import of an official constituency rank.

The 2024-election comparison uses the **2025 deprivation release**, not a 2024
deprivation dataset. A release year should not be interpreted as a common
collection year for every underlying indicator. Higher rank values mean less
deprivation, so their correlation signs differ in interpretation from mortality
or adverse-health prevalence.

Census measures come from 2021 in both election comparisons. The 2021
premature-ASMR workbook is linked by constituency code to 2019 voting only;
there is no 2024 boundary proxy or recalculated mortality rate.

## Acquiring the Files

```bash
python scripts/manage_data.py fetch
python scripts/manage_data.py verify
```

`fetch` delegates to the existing download helpers and then validates the entire
input manifest. It is not an instruction to accept whatever file is currently
served at a URL. Custom ONS output availability can change, and even a newly
generated export with similar content may differ byte-for-byte from the pinned
file. A mismatch stops verification; do not change a checksum merely to suppress
the failure.

Every required source has an unattended Python `requests` recipe. Notebook
startup invokes the complete fetch helper; no browser or manual file download
is needed. Downloads are staged, verified, then promoted into the local cache.
A checksum mismatch cannot overwrite an accepted input.

The former national temporal-context Section 5, its figure and both life-expectancy/
SII inputs have been removed. They are not needed by the constituency analysis.
Raw inputs and derived local data remain ignored by Git. Providers can still
remove or change historical downloads; in that case a fresh run fails explicitly.

### Election Version Identity

The original election workbooks were locally re-saved Excel files. Instead of
claiming those Excel container bytes can be downloaded, the pipeline retrieves
the official UK Parliament archive at commit
`9c31b89826873dfd1640bbb58bd7d8b3b56626ea`:

- [2019 CSV](https://raw.githubusercontent.com/ukparliament/psephology/9c31b89826873dfd1640bbb58bd7d8b3b56626ea/db/data/results-by-parliament/58/general-election/constituencies.csv)
- [2024 CSV](https://raw.githubusercontent.com/ukparliament/psephology/9c31b89826873dfd1640bbb58bd7d8b3b56626ea/db/data/results-by-parliament/59/general-election/constituencies.csv)

Every cell in all 650 original Excel rows matches after parsing 2019 dates and
removing two additional 2024 metadata columns (`County name`, `Declaration time`).
[election_sources.py](../src/election_sources.py) records the original Excel
hashes, the downloaded CSV hashes, and full parsed-table hashes. Both byte and
table checks run before the data are used. The table hashes include metadata,
all party counts, valid/invalid votes and electorates, not just chosen outcomes.

The current live 2024 workbook has revised electorate counts for Clapham and
Brixton Hill, Dulwich and West Norwood, Streatham and Croydon North, and Vauxhall
and Camberwell Green. Using it would change turnout. The versioned archive
preserves the exact original values without hard-coded corrections.

### Boundary and CSV Serialization

The official [2019 boundary archive](https://hub.arcgis.com/api/v3/datasets/11705b3f6efd4cc092580e269a86500f_0/downloads/data?format=shp&spatialRefId=27700)
and [2024 boundary archive](https://hub.arcgis.com/api/v3/datasets/0d698c9712de4afcac9377367d831c1a_0/downloads/data?format=shp&spatialRefId=27700)
provide the original geometry, index, projection and encoding files byte-for-byte.
The DBF exports contain extra provider columns and different number/UUID formatting.
[boundary_sources.py](../src/boundary_sources.py) restores the original schema,
serialization and export-metadata XML, without changing coordinates or attribute
values. Every resulting component must match its original byte count and SHA-256.
This preserves the original map data and spatial weights, not just similar boundaries.

The 2019 deprivation CSV is re-serialized with pandas and LF line endings,
reproducing the original cached file's bytes and values. All other Census,
deprivation and mortality workbooks match the original downloads directly.

## Mortality Snapshots

| Outcome | Pinned snapshot under `data/raw/mortality/snapshots/` |
|---|---|
| 2019/2024 ASMR | `pcondeathspopulations20192024_20261025T083750Z.xlsx` |
| 2021 premature ASMR | `premature_asmr_2021_20261025T085354Z.xlsx` |

The timestamp records when the snapshot was archived, not the mortality year.
Notebook startup checks both ONS downloads. Changed remote bytes cause a warning
and the verified snapshot is retained. A failed online check also warns and uses
the verified local snapshot. A corrupted local snapshot stops execution.

A missing snapshot is restored only from a local original or download matching
the pinned hash. `verify` does not access the network, but it can archive an
existing verified original workbook when the timestamped snapshot is absent.

## Interpretation and Result Integrity

Correlations are constituency-level, pairwise-complete associations. Reported
p-values are two-sided and unadjusted for multiple comparisons. Sample sizes can
differ by outcome and year; follow the notebook's exclusions and displayed `N`.
The Speaker's constituency is removed for correlation calculations after map
generation. Bivariate maps use shared, pooled-year quantile boundaries for the
corresponding variables; their appearance is not a new statistical estimate.

`python scripts/verify_results.py` checks the current correlation and p-value
tables, including sample sizes, against recorded hashes. It separately checks
the non-2021 rows against the historical baseline established before the 2021
addition. See [reproducibility.md](reproducibility.md) for the audit scope.
