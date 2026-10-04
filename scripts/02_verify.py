#!/usr/bin/env python3
"""Check every file under data/raw/<version>/ against its MANIFEST.json.

Re-hashes each file, tests each zip, counts the rows of every CSV in each zip
with the csv module and compares the data CSV with the row count the API
stated when it was fetched, and parses each JSON file. Prints ok/FAIL lines
and exits non-zero on any failure.

    uv run python scripts/02_verify.py
"""

import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def data_member(names: list[str]) -> str:
    data = [n for n in names if n.endswith(".csv") and n != "footnotes.csv"]
    if len(data) != 1:
        raise ValueError(f"expected one data CSV besides footnotes.csv, found {data}")
    return data[0]


def csv_rows_in_zip(path: Path) -> dict[str, int]:
    out = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            with z.open(name) as f:
                text = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
                out[name] = sum(1 for _ in csv.reader(text))
    return out


def check_zip(path: Path, entry: dict) -> list[str]:
    errors = []
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            return [f"corrupt member {bad}"]
    rows = csv_rows_in_zip(path)
    try:
        member = data_member(list(rows))
    except ValueError as e:
        return [str(e)]
    got = rows[member] - 1
    stated = entry.get("api_row_count")
    if stated is not None and got != stated:
        errors.append(f"{member} has {got} rows, the API stated {stated}")
    return errors


def main() -> int:
    failures = 0
    manifests = sorted(RAW.glob("*/MANIFEST.json"))
    if not manifests:
        print("FAIL no MANIFEST.json under data/raw/")
        return 1
    for mpath in manifests:
        d = mpath.parent
        for rel, entry in json.loads(mpath.read_text()).items():
            p = d / rel
            label = f"{d.name}/{rel}"
            if not p.exists():
                print(f"FAIL {label}: missing")
                failures += 1
                continue
            errors = []
            detail = ""
            if p.stat().st_size != entry["bytes"]:
                errors.append(f"size {p.stat().st_size} != {entry['bytes']}")
            if sha256(p) != entry["sha256"]:
                errors.append("sha256 mismatch")
            if p.suffix == ".zip":
                errors += check_zip(p, entry)
                detail = ", ".join(f"{n} {r - 1:,} rows" for n, r in csv_rows_in_zip(p).items())
            elif p.suffix == ".json":
                try:
                    detail = f"{len(json.loads(p.read_text())['items'])} items"
                except (ValueError, KeyError) as e:
                    errors.append(f"bad JSON: {e}")
            if errors:
                print(f"FAIL {label}: {'; '.join(errors)}")
                failures += 1
            else:
                print(f"ok   {label}: {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
