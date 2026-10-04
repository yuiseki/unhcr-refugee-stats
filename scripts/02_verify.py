#!/usr/bin/env python3
"""Check every file under data/raw/<version>/ against its MANIFEST.json, then the Parquet.

Raw: re-hashes each file, tests each zip, counts the rows of every CSV in each
zip with the csv module and compares the data CSV with the row count the API
stated when it was fetched, and parses each JSON file.

Parquet (data/parquet/<version>/, made by 03_export_parquet.py from UNHCR's
own series only):
  - every table of the rule is there, and nothing from third-party/
  - the row count equals that counted from the raw file with the csv module
    (or the items of countries.json), and the API's stated count
  - a sha256 over every value of every row, in order, equals the one taken
    from the raw file ("-" in a count column standing for NULL, an empty
    field for a NULL text), so no value was lost, changed or moved
  - the totals the API stated when the file was fetched equal the column sums
  - every column has the type the rule gives
  - the five zips carry the same footnotes.csv
  - a plain DuckDB, without extensions, opens every file
  - no row group carries a bloom filter

Prints ok/FAIL lines and exits non-zero on any failure.

    uv run python scripts/02_verify.py
"""

import csv
import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PQ = ROOT / "data" / "parquet"

_spec = importlib.util.spec_from_file_location("export", ROOT / "scripts" / "03_export_parquet.py")
export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export)

# the API's stated totals (MANIFEST.json, api_totals) and the CSV columns they sum
API_TOTALS = {
    "applied": "applied",
    "dec_recognized": "Recognized decisions",
    "dec_other": "Complementary protection",
    "dec_rejected": "Rejected decisions",
    "dec_closed": "Otherwise closed",
    "dec_total": "Total decisions",
    "returned_refugees": "Returned refugees",
    "resettlement": "Resettlement arrivals",
    "naturalisation": "Naturalisation",
    "returned_idps": "Returned IDPss",
}


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


def _row_hash(rows) -> tuple[int, str]:
    h = hashlib.sha256()
    n = 0
    for row in rows:
        h.update(json.dumps(row, ensure_ascii=False).encode())
        h.update(b"\n")
        n += 1
    return n, h.hexdigest()


def raw_csv_digest(zpath: Path, member: str) -> tuple[list[str], int, str]:
    """Header, data rows and a digest of every value, read with the csv module."""
    with zipfile.ZipFile(zpath) as z, z.open(member) as f:
        r = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))
        header = next(r)
        n, digest = _row_hash(r)
    return header, n, digest


def raw_json_digest(path: Path) -> tuple[list[str], int, str]:
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    keys = list(items[0])
    rows = ([None if i[k] is None else str(i[k]) for k in keys] for i in items)
    return (keys, *_row_hash(rows))


def parquet_digest(con, p: Path, types: dict[str, str], from_csv: bool) -> tuple[int, str]:
    """The same digest from the Parquet, its values written back as the source wrote them."""
    names = list(types)
    cur = con.execute(f"select * from read_parquet('{p}')")

    def text(v, t):
        if v is None:
            return None if not from_csv else ("-" if t == "BIGINT" else "")
        return str(v)

    def rows():
        while batch := cur.fetchmany(10000):
            for row in batch:
                yield [text(v, types[c]) for v, c in zip(row, names, strict=True)]

    return _row_hash(rows())


def check_parquet(version: str, check) -> None:
    import duckdb

    d = RAW / version
    out = PQ / version
    manifest = json.loads((d / "MANIFEST.json").read_text())
    con = duckdb.connect()
    con.execute("set memory_limit = '8GB'")
    plain = duckdb.connect(
        config={"autoinstall_known_extensions": False, "autoload_known_extensions": False}
    )
    want = {*export.TABLES, "footnotes", "countries"}
    have = {p.stem for p in out.glob("*.parquet")}
    check(have == want, f"{version}: Parquet tables {sorted(have)}, none from third-party/")

    sources = {t: (d / "unhcr" / f"{t}.zip", None) for t in export.TABLES}
    sources["footnotes"] = (d / "unhcr" / f"{export.FOOTNOTES_FROM}.zip", "footnotes.csv")
    sources["countries"] = (d / "unhcr" / "countries.json", None)

    for table in sorted(want & have):
        p = out / f"{table}.parquet"
        label = f"{version}/{table}.parquet"
        src, member = sources[table]
        if src.suffix == ".zip":
            with zipfile.ZipFile(src) as z:
                member = member or data_member(z.namelist())
            header, n_raw, digest_raw = raw_csv_digest(src, member)
        else:
            header, n_raw, digest_raw = raw_json_digest(src)
        types = dict(
            con.sql(
                f"select column_name, column_type from (describe select * from '{p}')"
            ).fetchall()
        )
        check(list(types) == header, f"{label}: columns and their order are the source's")
        wrong = {c: t for c, t in types.items() if t != export.column_type(table, c)}
        check(not wrong, f"{label}: every column has the type of the rule ({wrong or 'all'})")
        n_pq, digest_pq = parquet_digest(con, p, types, src.suffix == ".zip")
        check(
            n_pq == n_raw,
            f"{label}: {n_pq:,} rows, {n_raw:,} in the source (csv module, or JSON items)",
        )
        entry = manifest.get(f"unhcr/{table}.zip") or (
            manifest["unhcr/countries.json"] if table == "countries" else {}
        )
        stated = entry.get("api_row_count", entry.get("api_items"))
        if stated is not None:
            check(n_pq == stated, f"{label}: {n_pq:,} rows, the API stated {stated:,}")
        check(
            digest_pq == digest_raw,
            f"{label}: every value equals the source's (sha256 {digest_pq[:12]})",
        )
        for key, total in entry.get("api_totals", {}).items():
            col = API_TOTALS[key]
            got = con.sql(f"select sum(\"{col}\") from '{p}'").fetchone()[0]
            check(got == total, f"{label}: sum of {col} {got:,}, the API stated {total:,}")
        n_plain = plain.sql(f"select count(*) from read_parquet('{p}')").fetchone()[0]
        check(n_plain == n_pq, f"{label}: a DuckDB without extensions opens it")
        bloom = con.sql(
            f"select count(*) filter (where bloom_filter_offset is not null) from parquet_metadata('{p}')"
        ).fetchone()[0]
        check(bloom == 0, f"{label}: no bloom filters")

    footnotes = set()
    for t in export.TABLES:
        with zipfile.ZipFile(d / "unhcr" / f"{t}.zip") as z:
            footnotes.add(hashlib.sha256(z.read("footnotes.csv")).hexdigest())
    check(len(footnotes) == 1, f"{version}: the five zips carry the same footnotes.csv")


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

    def check(ok: bool, what: str) -> None:
        nonlocal failures
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            failures += 1

    for mpath in manifests:
        version = mpath.parent.name
        if not (PQ / version).is_dir():
            check(False, f"{version}: no Parquet, run scripts/03_export_parquet.py")
            continue
        check_parquet(version, check)
    print(f"\n{failures} checks failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
