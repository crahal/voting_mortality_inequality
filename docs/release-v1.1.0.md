# v1.1.0: Revised-Manuscript Replication Release

Release date: 27 October 2026.

This release includes the verified analysis and publication outputs through
commit `d7dcd9291e02e5fcd110ff5364a14ea24552f05c`, plus release metadata.

## Changes Since v1.0.1

- Added female and male 2021 premature-ASMR correlations throughout Section 4,
  compared with 2019 voting only. No 2024 boundary proxy is used.
- Added positive-vote sensitivity comparisons, regional adjustment,
  leave-one-region-out checks, 120 residual Moran tests and spatial-error models.
- Added requests-only retrieval of all required public inputs, pinned checksums,
  reusable timestamped mortality snapshots and upstream-change detection.
- Pinned the Python 3.12 analysis environment and added numerical regression
  checks, repository validation, synthetic-data tests and GitHub Actions.
- Updated scatter and bivariate-map presentation and PDF/SVG/800-dpi PNG exports.
  Table 1 includes coefficients, p-values and sample sizes for every outcome,
  including 2021 premature ASMR, and defines ASMR in its caption.
- Removed the separate Section 5 temporal-context analysis and its inputs at
  the author's request; it is not part of the retained-results comparison.

## Verification and Scope

The [fresh-download audit](download-audit.md) documents the successful
requirements-only, empty-data clone run on 25 October. It compared the rebuilt
analysis with the original local-data results, not a regenerated baseline.

Before this release, all 91 local tests passed and GitHub Actions passed for
`d7dcd92`. Coefficients, p-values and sample sizes were rechecked against pinned
baselines, including the historical results excluding 2021. All nine existing
robustness CSVs matched their original hashes. The spatial models were not
refitted as part of the final presentation-and-caption check.

The release-metadata update does not change analysis code, numerical baselines,
input checksums or generated results. Figure appearance and caption text have
changed; statistical results in the retained analyses have not.

Raw inputs remain excluded from Git and from this release archive. They must be
downloaded from the documented public sources under the providers' terms.
Reproduction depends on those sources remaining available and on the pinned
environment. Failed checks are not permission to replace the expected hashes.

The 2021 source is described as "premature" ASMR using the ONS release's label.
The age cut-off is not specified in the downloaded release documentation and
has not been assumed to be under 75.

## Citation

The [v1.1.0 GitHub release](https://github.com/crahal/voting_mortality_inequality/releases/tag/v1.1.0)
is archived at the version-specific DOI
[10.5281/zenodo.23690243](https://doi.org/10.5281/zenodo.23690243).
The release tag points to commit `30888f89b67dcfb8962dbefcbbb074ea905836c7`.
The downloaded Zenodo ZIP passed its published size and MD5 checksum check;
all 95 archived files matched the tag's Git blob hashes exactly. Its published
MD5 checksum is `2f37ea02b63d45cd3ce51abd31afd06c`.
The DOI was assigned after publication; this documentation-only follow-up adds
it without moving the release tag or changing any analysis files or outputs.

Rahal C. Replication materials for "Voting Patterns, Mortality, and Health
Inequalities in England: A replication and extension of Smith and Dorling (1996)"
[software]. Version v1.1.0. Zenodo; 2026.
https://doi.org/10.5281/zenodo.23690243.

The [archive-series DOI](https://doi.org/10.5281/zenodo.20508898) identifies all
versions, not a fixed numerical-analysis release.
