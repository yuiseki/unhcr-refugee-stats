import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dl = load("download", "01_download.py")
vf = load("verify", "02_verify.py")


def test_year_range_from_years_catalogue():
    years = json.loads((FIX / "years.json").read_text())
    assert dl.year_range(years) == (1951, 2027)


def test_year_range_rejects_empty_catalogue():
    with pytest.raises(ValueError):
        dl.year_range({"items": []})


def test_row_count_is_max_pages_at_limit_one():
    resp = json.loads((FIX / "count_asylum-decisions.json").read_text())
    assert dl.row_count(resp) == 113929
    assert dl.stated_totals(resp)["dec_total"] == 35497749


def test_stated_totals_empty_list_becomes_empty_dict():
    assert dl.stated_totals({"maxPages": 3, "total": []}) == {}


def test_row_count_rejects_missing_field():
    with pytest.raises(ValueError):
        dl.row_count({"items": []})


def test_query_url_full_period_download():
    url = dl.query_url("asylum-decisions", 1951, 2027, download=True)
    assert url == (
        "https://api.unhcr.org/population/v1/asylum-decisions/"
        "?yearFrom=1951&yearTo=2027&coo_all=true&coa_all=true&download=true"
    )


def test_query_url_count():
    url = dl.query_url("idmc", 1990, 2025, limit=1)
    assert url.endswith("/idmc/?yearFrom=1990&yearTo=2025&coo_all=true&coa_all=true&limit=1")


def test_files_are_split_by_provider():
    paths = {k: dl.relpath(k) for k in dl.UNHCR_KINDS + dl.THIRD_PARTY_KINDS}
    assert paths["population"] == "unhcr/population.zip"
    assert paths["demographics"] == "unhcr/demographics.zip"
    assert paths["idmc"] == "third-party/idmc.zip"
    assert paths["unrwa"] == "third-party/unrwa.zip"


def test_version_is_utc_fetch_date():
    assert dl.version_for(datetime(2026, 10, 4, 23, 59, tzinfo=UTC)) == "2026-10-04"


def test_countries_catalogue_is_one_page():
    resp = json.loads((FIX / "countries.json").read_text())
    assert dl.row_count(resp) == 1
    assert resp["items"][0]["iso"] == "AFG"


def test_data_member_skips_footnotes():
    assert vf.data_member(["idmc.csv", "footnotes.csv"]) == "idmc.csv"
    assert vf.data_member(["footnotes.csv", "asylum_decisions.csv"]) == "asylum_decisions.csv"


def test_data_member_requires_exactly_one():
    with pytest.raises(ValueError):
        vf.data_member(["footnotes.csv"])
    with pytest.raises(ValueError):
        vf.data_member(["a.csv", "b.csv", "footnotes.csv"])


def test_csv_rows_in_zip_counts_records_not_lines():
    rows = vf.csv_rows_in_zip(FIX / "idmc_trimmed.zip")
    # header + 4 data rows; footnotes has header + 2 rows with quoted commas
    assert rows == {"idmc.csv": 5, "footnotes.csv": 3}


def test_check_zip_compares_against_stated_count():
    entry = {"api_row_count": 4}
    assert vf.check_zip(FIX / "idmc_trimmed.zip", entry) == []
    errors = vf.check_zip(FIX / "idmc_trimmed.zip", {"api_row_count": 5})
    assert errors and "4" in errors[0]
