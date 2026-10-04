#!/usr/bin/env python3
"""Turn each version's UNHCR tables into typed Parquet, for the Hub viewer and DuckDB.

Only UNHCR's own series are exported: the five zips under unhcr/ and the
country list. The IDMC and UNRWA series under third-party/ are not (UNHCR's
Terms of Use for Datasets, item 6: third-party data may not be redistributed
without the provider's consent).

The type of a column comes from an explicit table, never from inference:

  - "Year" of the five data tables is INTEGER (four digits)
  - the count columns named in COUNTS, by their exact CSV heading (the
    source's misspelling "Returned IDPss" included), are BIGINT; the source
    writes "-" where it has no figure, which becomes NULL
  - "0" and "id" of the country list are INTEGER
  - everything else stays the text of the source, including the "Year" of
    footnotes.csv, which holds ranges such as "2018 - 2025", and any column
    this table does not name

A value that does not fit its type stops the run with the file, column and
value; nothing is rounded, trimmed or filled. Column names and row order are
those of the source.

    uv run python scripts/03_export_parquet.py
"""

import csv
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "parquet"
WORK = ROOT / "data" / "work"

TABLES = ["population", "asylum-applications", "asylum-decisions", "solutions", "demographics"]
# the five zips carry the same footnotes.csv; the one in population.zip is exported
FOOTNOTES_FROM = "population"

_DEMOGRAPHICS = [
    f"{sex} {band}"
    for sex in ("Female", "Male")
    for band in ("0 - 4", "5 - 11", "12 - 17", "18 - 59", "60", "other", "total")
] + ["Total"]

COUNTS = {
    "population": [
        "Refugees under UNHCR's mandate", "Asylum-seekers", "Returned refugees",
        "IDPs of concern to UNHCR", "Returned IDPss", "Stateless persons", "Others of concern",
        "Other people in need of international protection", "Host Community",
    ],
    "asylum-applications": ["applied"],
    "asylum-decisions": [
        "Recognized decisions", "Complementary protection", "Rejected decisions",
        "Otherwise closed", "Total decisions",
    ],
    "solutions": ["Returned refugees", "Resettlement arrivals", "Naturalisation", "Returned IDPss"],
    "demographics": _DEMOGRAPHICS,
}  # fmt: skip
INTEGERS = {"countries": ["0", "id"]}

COPY_OPTIONS = "format parquet, compression zstd, write_bloom_filter false"


def column_type(table: str, name: str) -> str:
    if table in TABLES and name == "Year":
        return "INTEGER"
    if name in COUNTS.get(table, ()):
        return "BIGINT"
    if name in INTEGERS.get(table, ()):
        return "INTEGER"
    return "VARCHAR"


def check_names(table: str, names: list[str]) -> None:
    """DuckDB matches names without case; two such names would clash."""
    seen: dict[str, str] = {}
    for n in names:
        if n.lower() in seen:
            raise ValueError(f"{table}: columns {seen[n.lower()]!r} and {n!r} clash in DuckDB")
        seen[n.lower()] = n


def _q(s: str) -> str:
    return s.replace("'", "''")


def _ident(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def _expr(file: str, table: str, name: str) -> str:
    c, t = _ident(name), column_type(table, name)
    where = f"{_q(file)}: {_q(name)}"
    if t == "VARCHAR":
        return c
    if t == "BIGINT":
        return (
            f"case when {c} is null then error('{where} is empty') "
            f"when {c} = '-' then null "
            f"when regexp_full_match({c}, '[0-9]+') then cast({c} as bigint) "
            f"else error('{where} is not a count or -: ' || {c}) end"
        )
    if table in TABLES:  # Year
        return (
            f"case when regexp_full_match({c}, '[0-9]{{4}}') then cast({c} as integer) "
            f"else error('{where} is not a year: ' || coalesce({c}, '(empty)')) end"
        )
    return (
        f"case when {c} is null then null "
        f"when regexp_full_match({c}, '-?[0-9]+') then cast({c} as integer) "
        f"else error('{where} is not an integer: ' || {c}) end"
    )


def select_sql(con, table: str, path: Path) -> str:
    src = f"read_csv('{_q(str(path))}', header = true, all_varchar = true, strict_mode = true)"
    names = con.sql(f"select * from {src} limit 0").columns
    check_names(table, names)
    cols = [f"{_expr(path.name, table, n)} as {_ident(n)}" for n in names]
    return f"select {', '.join(cols)} from {src}"


def countries_sql(con, path: Path, work: Path) -> str:
    """The API's country list, one row per item, keys as columns in their order."""
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    keys = list(items[0])
    for i, item in enumerate(items):
        if list(item) != keys:
            raise ValueError(f"{path.name}: item {i} has the keys {list(item)}, not {keys}")
    check_names("countries", keys)
    work.mkdir(parents=True, exist_ok=True)
    nd = work / "countries.ndjson"
    with open(nd, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    cols = "{" + ", ".join(f"'{_q(k)}': 'VARCHAR'" for k in keys) + "}"
    src = f"read_json('{_q(str(nd))}', format = 'newline_delimited', columns = {cols})"
    sel = [f"{_expr(path.name, 'countries', k)} as {_ident(k)}" for k in keys]
    return f"select {', '.join(sel)} from {src}"


def csv_rows(path: Path) -> int:
    """Records counted by the csv module; quoted fields may hold line breaks."""
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def data_member(names: list[str]) -> str:
    data = [n for n in names if n.endswith(".csv") and n != "footnotes.csv"]
    if len(data) != 1:
        raise ValueError(f"expected one data CSV besides footnotes.csv, found {data}")
    return data[0]


def versions() -> list[str]:
    return sorted(p.parent.name for p in RAW.glob("*/MANIFEST.json"))


def _write(con, sql: str, p: Path, expected: int) -> None:
    con.execute(f"copy ({sql}) to '{_q(str(p))}' ({COPY_OPTIONS})")
    got = con.sql(f"select count(*) from '{_q(str(p))}'").fetchone()[0]
    if got != expected:
        raise SystemExit(f"{p}: {got} rows written, the source has {expected}")
    print(f"{p.relative_to(ROOT)}: {got:,} rows, {p.stat().st_size:,} bytes", flush=True)


def main() -> int:
    import duckdb

    con = duckdb.connect()
    con.execute("set memory_limit = '8GB'")
    con.execute("set preserve_insertion_order = true")
    for version in versions():
        d = RAW / version / "unhcr"
        work = WORK / version
        out = OUT / version
        out.mkdir(parents=True, exist_ok=True)
        for table in TABLES:
            with zipfile.ZipFile(d / f"{table}.zip") as z:
                member = data_member(z.namelist())
                tw = work / table
                z.extract(member, tw)  # CRC checked by zipfile on read
                if table == FOOTNOTES_FROM:
                    z.extract("footnotes.csv", tw)
            src = tw / member
            _write(con, select_sql(con, table, src), out / f"{table}.parquet", csv_rows(src))
            if table == FOOTNOTES_FROM:
                fn = tw / "footnotes.csv"
                _write(
                    con, select_sql(con, "footnotes", fn), out / "footnotes.parquet", csv_rows(fn)
                )
        cj = d / "countries.json"
        n = len(json.loads(cj.read_text(encoding="utf-8"))["items"])
        _write(con, countries_sql(con, cj, work), out / "countries.parquet", n)
        shutil.rmtree(work)
    if WORK.exists() and not any(WORK.iterdir()):
        WORK.rmdir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
