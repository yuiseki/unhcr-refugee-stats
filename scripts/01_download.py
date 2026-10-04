#!/usr/bin/env python3
"""Fetch the UNHCR Refugee Population Statistics Database from its public API.

Source: https://api.unhcr.org/population/v1/ (documented at
https://api.unhcr.org/docs/refugee-statistics.html, no key required).

The database is overwritten in place twice a year and the API has no
parameter for choosing a release, so the version is the fetch date (UTC,
YYYY-MM-DD). Files go to:

    data/raw/<YYYY-MM-DD>/unhcr/        population, asylum-applications,
                                        asylum-decisions, solutions,
                                        demographics, and the countries list
    data/raw/<YYYY-MM-DD>/third-party/  idmc and unrwa (data UNHCR receives
                                        from IDMC and UNRWA; item 6 of the
                                        Terms of Use for Datasets may apply)

The year range comes from the API's own years endpoint. For every kind the
API's full-period download is used (download=true with coo_all and coa_all,
one row per year, country of origin and country of asylum); it returns a zip
holding the data CSV and footnotes.csv, kept as served. Before each download
the row count the API states (maxPages of a limit=1 query) is recorded, and
the CSV in the zip must have exactly that many rows.

data/raw/<version>/MANIFEST.json records url, bytes, sha256, last_modified,
fetched_at and what the API stated. A file already in the manifest whose
sha256 still matches is not fetched again. Requests are sequential and at
least 1 second apart.

    uv run python scripts/01_download.py
"""

import csv
import hashlib
import io
import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
API = "https://api.unhcr.org/population/v1"
UA = "unhcr-refugee-stats/1 (+https://github.com/yuiseki/unhcr-refugee-stats)"
UNHCR_KINDS = ["population", "asylum-applications", "asylum-decisions", "solutions", "demographics"]
THIRD_PARTY_KINDS = ["idmc", "unrwa"]
COUNTRIES = "unhcr/countries.json"
MIN_INTERVAL = 1.5

_last_request = 0.0


def version_for(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%d")


def relpath(kind: str) -> str:
    folder = "third-party" if kind in THIRD_PARTY_KINDS else "unhcr"
    return f"{folder}/{kind}.zip"


def query_url(kind: str, year_from: int, year_to: int, **extra) -> str:
    params = {"yearFrom": year_from, "yearTo": year_to, "coo_all": "true", "coa_all": "true"}
    for k, v in extra.items():
        params[k] = str(v).lower() if isinstance(v, bool) else v
    return f"{API}/{kind}/?{urllib.parse.urlencode(params)}"


def year_range(resp: dict) -> tuple[int, int]:
    years = [int(item["year"]) for item in resp.get("items", [])]
    if not years:
        raise ValueError("the years endpoint returned no years")
    return min(years), max(years)


def row_count(resp: dict) -> int:
    if "maxPages" not in resp:
        raise ValueError("response has no maxPages")
    return int(resp["maxPages"])


def stated_totals(resp: dict) -> dict:
    total = resp.get("total")
    return total if isinstance(total, dict) else {}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _open(url: str):
    global _last_request
    wait = _last_request + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=600)


def get_json(url: str) -> dict:
    with _open(url) as r:
        return json.load(r)


def fetch(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _open(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
        length = r.headers.get("Content-Length")
        lm = r.headers.get("Last-Modified", "")
    got = tmp.stat().st_size
    if length is not None and got != int(length):
        tmp.unlink()
        raise SystemExit(f"{url}: got {got} bytes, the server stated {length}")
    tmp.replace(dest)
    return {
        "url": url,
        "bytes": got,
        "sha256": sha256(dest),
        "last_modified": lm,
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def zip_data_rows(path: Path) -> dict[str, int]:
    """Rows (header included) of every CSV in the zip."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            with z.open(name) as f:
                text = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
                out[name] = sum(1 for _ in csv.reader(text))
    return out


def is_current(d: Path, manifest: dict, rel: str) -> bool:
    return rel in manifest and (d / rel).exists() and sha256(d / rel) == manifest[rel]["sha256"]


def main() -> int:
    version = version_for(datetime.now(UTC))
    d = RAW / version
    d.mkdir(parents=True, exist_ok=True)
    mpath = d / "MANIFEST.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}

    def save():
        mpath.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")

    wanted = [COUNTRIES] + [relpath(k) for k in UNHCR_KINDS + THIRD_PARTY_KINDS]
    if all(is_current(d, manifest, rel) for rel in wanted):
        print(f"{version}: all {len(wanted)} files present and unchanged, nothing fetched")
        return 0

    years_url = f"{API}/years/?limit=1000"
    y0, y1 = year_range(get_json(years_url))
    print(f"{version}: years {y0}-{y1} (from {years_url})")

    if not is_current(d, manifest, COUNTRIES):
        url = f"{API}/countries/?limit=1000"
        entry = fetch(url, d / COUNTRIES)
        resp = json.loads((d / COUNTRIES).read_text())
        if row_count(resp) != 1:
            raise SystemExit(f"{url}: countries span {row_count(resp)} pages, expected 1")
        entry["api_items"] = len(resp["items"])
        manifest[COUNTRIES] = entry
        save()
        print(f"{COUNTRIES}: {entry['bytes']:,} bytes, {entry['api_items']} countries")

    for kind in UNHCR_KINDS + THIRD_PARTY_KINDS:
        rel = relpath(kind)
        if is_current(d, manifest, rel):
            print(f"{rel}: already fetched")
            continue
        count_url = query_url(kind, y0, y1, limit=1)
        resp = get_json(count_url)
        stated = row_count(resp)
        entry = fetch(query_url(kind, y0, y1, download=True), d / rel)
        rows = zip_data_rows(d / rel)
        data = [n for n in rows if n != "footnotes.csv"]
        if len(data) != 1 or rows[data[0]] - 1 != stated:
            (d / rel).unlink()
            raise SystemExit(
                f"{rel}: zip rows {rows} do not match the {stated} rows the API states"
            )
        entry.update(
            {
                "year_from": y0,
                "year_to": y1,
                "api_row_count": stated,
                "api_row_count_url": count_url,
                "api_totals": stated_totals(resp),
                "csv_rows_with_header": rows,
            }
        )
        manifest[rel] = entry
        save()
        print(f"{rel}: {entry['bytes']:,} bytes, {stated:,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
