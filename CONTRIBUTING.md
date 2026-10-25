# Contributing

This is a research repository. Changes should make the analysis clearer or more
reproducible without silently changing its population, outcomes or results.

## Development

Use Python 3.12 and install `requirements-dev.txt` in an isolated environment.
Run from the repository root:

```bash
python -m ruff check .
python scripts/check_repository.py
python -m unittest discover -s tests -v
```

Tests must run without research data or live network access. Use small synthetic
fixtures and mock downloads. Keep changes focused; avoid moving the helper
module or stripping notebook outputs solely to satisfy a formatting preference.
Saved notebook results are part of the reader-facing research record.

## Changes Affecting Results

For data readers, joins, exclusions, scientific dependencies or statistical
functions, also run the following with the verified local inputs:

```bash
python scripts/manage_data.py verify
python scripts/verify_results.py
```

Do not update source checksums or expected-result hashes just to make a check
pass. An intended analytical change should document the source/version change,
affected variables, coefficients, p-values and sample sizes, and why the change
is necessary. Keep it separate from purely presentational changes.

For plotting changes, compare data coordinates, colour assignments, map bins,
axis ranges and annotation targets as well as inspecting the figures. Regenerate
the relevant PDF, SVG, 800-dpi PNG and notebook previews together. Preserve the
distinction between 2021 premature ASMR and the 2019/2024 ASMR series.

## Data and Privacy

Never commit `data/`, mortality snapshots, credentials, environment files or raw
datasets to an issue. Link to a public source and provide a synthetic example
instead. Existing ignored manuscript and local configuration paths remain local.

## Pull Requests and Releases

Explain the change, list the checks run and state whether results change.
Publication outputs are marked as generated in GitHub diffs, but should still
be reviewed when regenerated. Automatic dependency updates are limited to GitHub
Actions; scientific package updates need numerical verification.

Before a release, run repository tests and empirical verification, execute the
notebook with the verified environment, inspect outputs, and check the citation
metadata against the corresponding archive. Do not label unreleased changes as
the contents of an older Zenodo release. Include the commit and environment in
the release notes. The [reproduction guide](docs/reproducibility.md) documents the
commands and expected checks.
