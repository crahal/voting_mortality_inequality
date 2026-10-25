"""Inspect, fetch or verify the existing pinned input manifest."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import helpers


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["sources", "fetch", "verify"])
    args = parser.parse_args(argv)
    if args.command == "sources":
        print(helpers.raw_data_sources_markdown())
    else:
        helpers.ensure_raw_data(download=args.command == "fetch", verify=True)


if __name__ == "__main__":
    main()
