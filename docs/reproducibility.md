# Reproducing and Verifying the Analysis

[Project overview](../README.md) | [Data provenance](data.md)

## Environment

Use Python 3.12 and a dedicated environment. The reference run used Python
3.12.7. [requirements.txt](../requirements.txt) pins the scientific, geospatial
and notebook packages used for the verified results, including the notebook
kernel. [requirements-dev.txt](../requirements-dev.txt) adds repository checks.
[requirements-constraints.txt](../requirements-constraints.txt) also pins the
transitive versions from the verified Python 3.12.7/Linux run and is loaded
automatically by `requirements.txt`. It does not force Linux-only extras onto
other platforms. Native-library/platform differences are still possible; the
numerical checks must pass before claiming an equivalent reproduction.

The first notebook cell and both analysis/verification commands check the runtime
versions against `requirements.txt` before loading data. A mismatch lists the
packages and active Python executable; switch to the pinned kernel and restart.

From the repository root in a VS Code terminal, run the notebook directly with
`.venv/bin/python scripts/run_analysis.py`. This uses the verified environment
without selecting a notebook kernel or changing the terminal's default Python.
Saved-file messages and diagnostic file paths are relative to the current working
directory (`../output/...` inside the notebook, `output/...` at the repository root).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip check
```

On Windows, use `py -3.12 -m venv .venv` and activate with
`.venv\Scripts\Activate.ps1` in PowerShell. Commands below work from the repository
root without Make. `make help` lists equivalent shortcuts on systems with Make.

Geospatial wheels include native dependencies on supported platforms. If a
platform needs a separate native-library installation, record that environment
and run the result checks before treating it as an equivalent reproduction.
Figure exports require installed Helvetica Regular, Bold, Oblique and Bold
Oblique fonts, including for mathematical symbols. Install licensed copies using
your operating system's font installer and restart the notebook kernel. These
fonts are not distributed with this repository or installed by pip. Exports fail
with an explicit error if Helvetica is unavailable instead of substituting a
different family. PDFs embed the fonts; SVGs preserve glyphs as vector outlines.
This font prerequisite does not affect numerical verification with
`python scripts/verify_results.py`. Rendering libraries can still affect figure
bytes without changing statistics. PNG export at 800 dpi is memory-intensive.

## Checks Without Research Data

```bash
python -m ruff check .
python scripts/check_repository.py
python -m unittest discover -s tests -v
```

These commands validate Python syntax/name errors, notebook schema and cell
syntax, saved notebook errors, local documentation links, YAML metadata, snapshot
safety, table construction and plotting contracts. Tests use synthetic data and
mock downloads; no research dataset or external service is required.

[GitHub Actions](../.github/workflows/checks.yml) runs those checks on pushes and
pull requests. It has read-only repository permissions, pinned action revisions
and no publishing step. A passing CI run is **not** evidence that the full
empirical analysis was rerun; the input data are intentionally not in Git.

## Verify the Empirical Results

Download and verify all inputs with `requests`, then check the empirical results:

```bash
python scripts/manage_data.py fetch
python scripts/manage_data.py verify
python scripts/verify_results.py
```

The verification command rebuilds the constituency datasets, applies the
notebook's England and Speaker exclusions and recomputes the summary tables.
It does not render figures or rewrite the notebook, Word tables or result
fixtures. No network access is required once verified local inputs are present.

[summary_hashes.json](../tests/fixtures/summary_hashes.json) records hashes of
the serialized coefficient and p-value tables, including their `N` columns.
The serialization matches the notebook's existing hash convention:
`table.round(12).to_csv(index=False)`, encoded as UTF-8 and hashed with SHA-256.
The legacy summary tables have object-typed numeric columns, which pandas does
not round with this call. These preserved reference hashes therefore also detect
floating-point differences at full serialization precision. A different NumPy
version can trigger a mismatch even when published coefficients are unchanged;
verify the environment and actual values rather than replacing the hashes.

The baseline includes the additional 2021 outcomes and separate checks for the
original non-2021 rows. The latter were independently compared against commits
`4ec7a45` and `876b65c`: all 120 coefficients, 120 p-values and associated sample
sizes matched exactly, as did the original data-file checksums. A failed hash
check must be investigated, not resolved by automatically replacing the fixture.

The full notebook runner also checks all nine robustness CSVs against
[robustness_hashes.json](../tests/fixtures/robustness_hashes.json), captured from
the original local-data run. These include positive-vote comparisons, regional
models, Moran diagnostics, spatial-error models, leave-one-region-out checks,
coverage and all spatial-weight edges. This is a byte-level check, including
full-precision values. A platform-dependent numerical difference fails the check
and needs investigation rather than automatic acceptance.

## Regenerate Publication Outputs

From a fresh clone (no local data needed):

```bash
python scripts/run_analysis.py
```

This executes the notebook from the first cell to the last using the current
Python executable as its kernel. Startup fetches all missing inputs using
`requests`, verifies every file, and checks both mortality downloads against
the pinned snapshots. No browser is used. The command checks numerical-result
hashes before saving the successfully executed notebook. It regenerates:

| Destination | Contents |
|---|---|
| `src/analysis.ipynb` | Executed analysis, statistics and inline tables |
| `output/figures/` | PDF, SVG and 800-dpi PNG figures |
| `output/tables/` | Main and full correlation/p-value Word tables |
| `data/derived/` | CSV inputs for inspecting map calculations; ignored by Git |

An interactive editor can also run all notebook cells in order, using the
project environment as its Python kernel. Do not use a globally installed
kernel with different scientific dependencies by accident.

After activating `.venv`, register an explicitly named kernel:

```bash
python -m pip check
python -m ipykernel install --user --name voting-mortality-inequality --display-name "Voting mortality (pinned)"
```

Select **Voting mortality (pinned)** in the notebook, restart its kernel and run
the cells in order. Activating an environment in a terminal does not switch an
already-running notebook kernel. If you move the repository, register the kernel
again so its Python path points to the new location.
The notebook's saved kernel metadata now names this kernel explicitly. The
command-line runner instead uses the Python executable that launched it.

## Troubleshooting

| Symptom | Action |
|---|---|
| Missing data or shapefile component | Rerun `python scripts/manage_data.py fetch`; an incomplete boundary bundle is fetched and verified automatically. |
| Provider unavailable or removed historical version | Retry later. A fresh run needs network access and the pinned upstream versions; the pipeline stops rather than substitutes different data. |
| Local checksum mismatch | Preserve the suspect file for investigation and obtain the pinned version. Do not overwrite the expected checksum. |
| Remote ASMR hash warning | The provider changed the remote file; the verified local snapshot is still used. |
| Cannot check ONS online | The warning identifies the failed check. An intact local snapshot remains usable. |
| Correlation or p-value hash mismatch | Check input identity, Python/dependency versions, exclusions and boundary joins. Treat this as a potential analytical change. |
| Notebook kernel unavailable | Activate the environment and install its requirements, which include `ipykernel`. |
| pip conflicts involving unrelated packages, or NumPy/scikit-learn versions above the pinned versions | Use the dedicated `.venv`, install `requirements.txt` there and select its notebook kernel. Do not upgrade individual scientific packages in a shared Anaconda environment or change the verified pins to satisfy another project. |
| Different figure bytes with unchanged statistics | Check fonts, renderer versions and file metadata; PDF/SVG/PNG bytes are not numerical-result hashes. |

For a reproducible report, record `git rev-parse HEAD`, `python --version`, the
result-verification output and `python -m pip freeze`. See
[CONTRIBUTING.md](../CONTRIBUTING.md) before changing scientific dependencies,
source versions or baseline hashes.
