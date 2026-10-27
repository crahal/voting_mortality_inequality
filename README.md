# Voting Patterns, Mortality, and Health Inequalities in England

[![Checks](https://github.com/crahal/voting_mortality_inequality/actions/workflows/checks.yml/badge.svg)](https://github.com/crahal/voting_mortality_inequality/actions/workflows/checks.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB)](requirements.txt)
[![License: GPL v3](https://img.shields.io/badge/License-GPL_v3-blue.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23690243.svg)](https://doi.org/10.5281/zenodo.23690243)

Research code and publication outputs examining associations between voting,
mortality and health inequalities across English parliamentary constituencies.
The analysis replicates and extends the constituency-level approach of Smith
and Dorling's 1996 BMJ study using the 2019 and 2024 general elections.

**[Read the analysis](src/analysis.ipynb) | [Figures](output/figures) | [Tables](output/tables) | [Data sources](docs/data.md) | [Reproduce results](docs/reproducibility.md)**

<img src="assets/header_asmr.png" width="760" alt="Bivariate constituency maps illustrating the relationship between voting and age-standardised mortality in England" />

## Research Scope

| Component | Coverage |
|---|---|
| Elections | Constituency vote shares and voter turnout, 2019 and 2024 |
| Main mortality outcomes | Female and male ASMR for deaths registered in 2019 and 2024 |
| Additional mortality outcome | Female and male **2021 premature ASMR**, compared with **2019 voting only** |
| Census outcomes | Census 2021 general health, disability and unpaid care, on each election's boundaries |
| Deprivation | Health Deprivation and Disability: 2019 LSOA aggregation and the 2025 constituency release |
| Statistics | Spearman and Pearson correlations, two-sided p-values and sample sizes |
| Robustness | Positive-vote comparisons; regional adjustment, Moran's I and spatial-error models |

This is a **descriptive, ecological analysis**, not a causal analysis or an
individual-level study. The 2021 premature-ASMR outcome is distinct from the
main ASMR series; it is not reassigned to the revised 2024 boundaries.
Deprivation ranks run in the opposite direction to mortality and adverse-health
prevalence: a higher rank indicates **less** deprivation.

## Start Here

To inspect the findings, open the [executed notebook](src/analysis.ipynb) or the
publication files below. No local data or software installation is needed.

| Output | Files |
|---|---|
| Labour vote share and mortality | [Scatter PDF](output/figures/labour_asmr_scatter.pdf), [map PDF](output/figures/labour_asmr_bivariate_choropleth.pdf) |
| Health and disability | [Bivariate map PDF](output/figures/labour_census_health_disability_bivariate_choropleth.pdf) |
| Main Table 1: all correlations, including 2021 premature ASMR, unpaid care and deprivation | [Word document](output/tables/full_correlation_and_p_value_table.docx) |
| Optional compact online summary (excludes unpaid care and deprivation) | [Word document](output/tables/correlation_and_p_value_tables.docx) |

Figures are exported as **PDF, SVG and 800-dpi PNG**. The figure directory also
contains the Conservative, Liberal Democrat and turnout comparisons. Section 4
of the notebook displays the coefficient and p-value tables inline.

## Quick Start

Use **Python 3.12**. The pinned scientific packages match the environment used
for the verified results; they are not a request to upgrade an existing environment.

```bash
git clone https://github.com/crahal/voting_mortality_inequality.git
cd voting_mortality_inequality
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/check_repository.py
python -m unittest discover -s tests -v
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell.
Use `requirements.txt` instead if you only need the analysis environment.

### Reproduce the Analysis

Raw data are **not redistributed in this repository**. Notebook startup fetches
all required inputs, including both boundary datasets, using Python `requests`.
No browser, sign-in or manual file download is required. The pinned versions and
checksums preserve the original analysis; a changed source is never silently accepted.

```bash
python scripts/run_analysis.py
```

This runs every cell with the active environment's Python kernel, downloads
missing inputs and regenerates publication outputs, then checks the correlation,
p-value and sample-size hashes. Running all cells in the notebook also fetches
the data automatically. Use `python scripts/manage_data.py fetch` to fetch only,
or `verify` and `python scripts/verify_results.py` for offline checks after download.
See the [reproduction guide](docs/reproducibility.md) for prerequisites, checks
and troubleshooting. Equivalent shortcuts are listed by `make help`.

## Reproducibility Checks

The [fresh-download audit](docs/download-audit.md) records the completed
requests-only, empty-data run and comparison with the original local analysis.

- **Input identity:** pinned file sizes, SHA-256 checksums and schema checks.
- **Environment:** direct and transitive dependency versions pinned to the verified run.
- **Mortality snapshots:** timestamped local copies are reused; changed ONS
  downloads trigger a warning and never silently replace the analysis inputs.
- **Numerical regression:** coefficient, p-value and sample-size table hashes,
  including the pre-2021 baseline, are checked by `scripts/verify_results.py`.
  The full runner also checks all nine robustness CSVs against their original hashes.
- **Continuous integration:** syntax/name checks, notebook validation,
  documentation links and synthetic-data unit tests. CI does **not** download
  research data or claim to reproduce the full empirical analysis.

## Repository Layout

```text
src/analysis.ipynb       Executed analysis and source links
src/helpers.py          Data preparation, statistics, plotting and exports
scripts/                Data, result-verification and repository-check commands
tests/                  Synthetic-data tests and numerical hash fixtures
docs/                   Data provenance and reproduction guides
.github/                CI, dependency maintenance and contribution templates
assets/                 README imagery
output/figures/         Publication figures: PDF, SVG and 800-dpi PNG
output/tables/          Main Table 1, compact online summary and robustness CSVs
data/                   Local inputs, snapshots, boundaries and derived CSVs (ignored)
```

The notebook is the orchestration layer. Source-specific verification is in
`election_sources.py` and `boundary_sources.py`; spatial checks are in
`spatial_robustness.py`. Data preparation and publication exports remain in `helpers.py`.

## Citation and Contributions

The current release is
[`v1.1.0`](https://github.com/crahal/voting_mortality_inequality/releases/tag/v1.1.0).
See its [release notes](docs/release-v1.1.0.md) for the changes and verification.
Its version-specific Zenodo DOI is
[10.5281/zenodo.23690243](https://doi.org/10.5281/zenodo.23690243).
Cite this archive, not the earlier `v1.0.1` archive, for the current analysis.
[CITATION.cff](CITATION.cff) provides the citation metadata. For development
changes after a release, also record the Git commit used; the working tree is
not necessarily identical to the archived release.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development checks and the policy for
changes to data or results. Use the repository's
[issue tracker](https://github.com/crahal/voting_mortality_inequality/issues)
for software problems or questions about the analysis. Do not attach raw data.

## Acknowledgements and License

The bivariate mapping implementation builds on
[Suzuki Shosuke's public choropleth examples](https://github.com/shosuke-13/Japan-Bivariate-Choroplethmaps).

Financial support was received from the Leverhulme Trust for the Leverhulme
Centre for Demographic Science (grant RC-2018-003), Nuffield College, and the
Health Foundation REAL Demand Unit.

The repository is released under the [GNU General Public License v3.0](LICENSE).
Source datasets remain subject to their providers' terms; the code license does
not grant redistribution rights for those datasets.
