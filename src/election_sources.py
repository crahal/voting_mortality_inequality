"""Versioned Parliament tables verified against the original local Excel data."""

import hashlib

import pandas as pd


ARCHIVE_COMMIT = "9c31b89826873dfd1640bbb58bd7d8b3b56626ea"
ARCHIVE_ROOT = f"https://raw.githubusercontent.com/ukparliament/psephology/{ARCHIVE_COMMIT}"
ELECTION_SOURCES = {
    2019: {
        "path": "data/raw/voting/HoC-GE2019-results-by-constituency.csv",
        "sha256": "447288168ce9850a3e41b79aeb2c637e059fcb3c23d64d6566535e5d5d7fb394",
        "size": 127736,
        "table_sha256": "763748ebb3e44f1c93a5b89878dd3ce63e649f9777859dbd356243191057b458",
        "original_xlsx_sha256": "18a183e5dbf243c898ebcaed2df7d5b86fe18f2d7fb0ba9af203e26e3a76e36a",
        "source": "https://commonslibrary.parliament.uk/research-briefings/cbp-8749/",
        "download": f"{ARCHIVE_ROOT}/db/data/results-by-parliament/58/general-election/constituencies.csv",
        "note": "Official versioned Parliament CSV; all 650 rows match the original Excel Data sheet after date parsing.",
    },
    2024: {
        "path": "data/raw/voting/HoC-GE2024-results-by-constituency.csv",
        "sha256": "bdc0eff07722a21c80b2ecaaf37b7b220cdd778499f1a30637bce249d77d006d",
        "size": 116067,
        "table_sha256": "520d0580f84c3969f260adaf180a607d9b5f1adb85845fdbc7474f77aaf40371",
        "original_xlsx_sha256": "41c220a08c662f60750477e60c672149ad0b126bf3d7cedddea1b8f1748c05bc",
        "source": "https://commonslibrary.parliament.uk/research-briefings/cbp-10009/",
        "download": f"{ARCHIVE_ROOT}/db/data/results-by-parliament/59/general-election/constituencies.csv",
        "note": "Official versioned Parliament CSV; all 650 original Excel rows match, including original electorate counts.",
    },
}
HEADERS_2019 = [
    "ONS ID", "ONS region ID", "Constituency name", "County name", "Region name",
    "Country name", "Constituency type", "Declaration time", "Member first name",
    "Member surname", "Member gender", "Result", "First party", "Second party",
    "Electorate", "Valid votes", "Invalid votes", "Majority", "Con", "Lab", "LD",
    "BRX", "Green", "SNP", "PC", "DUP", "SF", "SDLP", "UUP", "APNI",
    "All other candidates", "Of which other winner",
]


def read_election_results(root, year):
    spec = ELECTION_SOURCES[year]
    path = root / spec["path"]
    content = path.read_bytes()
    if len(content) != spec["size"] or hashlib.sha256(content).hexdigest() != spec["sha256"]:
        raise ValueError(f"{year} election download does not match the pinned original version.")
    if year == 2019:
        frame = pd.read_csv(path, header=None, names=HEADERS_2019)
        frame["Declaration time"] = pd.to_datetime(frame["Declaration time"], format="%d/%m/%Y %H:%M")
    else:
        frame = pd.read_csv(path).drop(columns=["County name", "Declaration time"])
    if len(frame) != 650 or not frame["ONS ID"].is_unique:
        raise ValueError(f"{year} election constituency coverage changed.")
    table_hash = hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    if table_hash != spec["table_sha256"]:
        raise ValueError(f"{year} election table differs from the original Excel analysis inputs: {table_hash}")
    return frame
