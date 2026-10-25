"""Recompute correlation tables offline without rewriting the notebook or outputs."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analysis_environment import validate_analysis_environment
import helpers


def table_hash(table):
    return hashlib.sha256(table.round(12).to_csv(index=False).encode()).hexdigest()


def check_tables(coefficients, p_values, expected):
    tables = {"coefficients": coefficients, "p_values": p_values}
    for name, table in list(tables.items()):
        tables[name + "_without_2021"] = table.loc[
            ~table["Variable"].str.startswith("PrematureASMR2021_")
        ].reset_index(drop=True)
    for name, table in tables.items():
        actual = table_hash(table)
        if actual != expected[name]:
            raise ValueError(f"{name} changed: {actual}; expected {expected[name]}")


def verify_exported_robustness():
    """Check all saved robustness values, geography weights and sample sizes."""
    baseline = json.loads((ROOT / "tests/fixtures/robustness_hashes.json").read_text())
    for name, expected in baseline["files"].items():
        actual = hashlib.sha256((ROOT / "output/tables" / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"{name} changed: {actual}; expected {expected}")
    print(f"PASS: all {len(baseline['files'])} robustness CSVs match the original-local-data baseline byte-for-byte.")


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    validate_analysis_environment()
    baseline = json.loads((ROOT / "tests/fixtures/summary_hashes.json").read_text())
    helpers.ensure_raw_data(download=False, verify=True)
    for year in [2019, 2024]:
        frame = helpers.make_merged(year)
        frame = frame.loc[frame["First party"].notna()].copy()
        geography = helpers.make_df_gpd(year, frame)
        geography = geography.loc[
            geography["Country name"].eq("England") & geography["First party"].ne("Spk")
        ].copy()
        coefficients, p_values = helpers.make_summary_tables(frame, geography, str(year))
        helpers.validate_summary_table_hash(coefficients, year)
        check_tables(coefficients, p_values, baseline["years"][str(year)])
        print(f"PASS {year}: coefficients, p-values and sample sizes match; "
              "the non-2021 results also match their historical baseline.")


if __name__ == "__main__":
    main()
