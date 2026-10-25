# Fresh-Download Reproduction Audit

[Reproduction instructions](reproducibility.md) | [Data provenance](data.md)

## Verification Performed

On 25 October 2026, the analysis was run in a separate project directory with
**no existing `data/` directory** and a newly created Python 3.12.7 environment.
All notebook cells executed in order, using the versions in `requirements.txt`
and `requirements-constraints.txt`. Downloads used standard Python `requests`.
No browser, Selenium, Playwright or `curl_cffi` was installed in that environment.
No original local data were copied into the reproduction directory.

Before changing the original pipeline, its local election tables, merged data,
geometries, summary tables, manuscript statistics and publication tables were
captured separately as the comparison baseline. The new run was compared against
those results, not against a freshly regenerated expectation from the new inputs.

## Results

| Check | Outcome |
|---|---|
| All 26 required input files/components | Pinned byte counts and SHA-256 checks passed, including both mortality snapshots and all boundary components. |
| Election data | Every original Excel Data-sheet cell matched: 650 rows in each year, including electorates, valid/invalid votes and all party counts. |
| Merged analysis data and map geometries | Exact dataframe equality for both years, including dtypes and all values. |
| Section 4 main tables | All 140 coefficients, 140 p-values and 28 row-specific sample sizes exactly equal, including 2021 outcomes. |
| Pre-2021 results | Historical non-2021 coefficient/p-value/N hashes unchanged. |
| Manuscript statistics | Leader-constituency ASMR/CI values, party means and printed statistics exactly equal. |
| Zero-vote robustness | All 140 rows unchanged. |
| Regional/spatial robustness | All eight CSVs unchanged, including 120 Moran tests, 60 spatial-error models, 270 leave-one-region-out fits and 11,080 directed weight edges. |
| Saved robustness files | All nine CSVs byte-for-byte identical to the original local-data run. |
| Publication tables | All text and table values in both Word documents exactly equal. |
| Notebook and figures | All cells completed without errors; 12 figures regenerated in PDF, SVG and 800-dpi PNG. |

The old Section 5 temporal-context analysis and its two inputs were intentionally
removed at the author's request. It is not part of the retained-results comparison.

## Identity and Limits

The public election CSV containers are not the original locally re-saved Excel
containers. Their complete parsed tables are identical, verified independently
of the download hashes. See [data provenance](data.md#election-version-identity).
Boundary DBF and metadata serialization is restored before checking every original
component hash; geometry is not changed.

The recorded checks do not guarantee permanent availability of third-party URLs
or bitwise-identical floating-point computation on every platform. Source changes
and numerical differences fail verification rather than silently changing results.
An existing valid mortality snapshot remains usable, with a warning if its online
source changes. Figure files can differ in metadata or rendering without changing
their plotted data; their binary identity is not used as a statistical check.

Raw inputs and snapshots remain gitignored. The manuscript Word file supplied
for provenance was read only and was not modified.
