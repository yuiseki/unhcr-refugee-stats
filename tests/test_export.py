import importlib.util
import json
from pathlib import Path

import duckdb
import pytest

_spec = importlib.util.spec_from_file_location(
    "export", Path(__file__).parents[1] / "scripts" / "03_export_parquet.py"
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


@pytest.mark.parametrize(
    ("table", "name", "sql"),
    [
        ("population", "Year", "INTEGER"),
        ("population", "Refugees under UNHCR's mandate", "BIGINT"),
        ("population", "Returned IDPss", "BIGINT"),
        ("population", "Other people in need of international protection", "BIGINT"),
        ("population", "Country of origin", "VARCHAR"),
        ("population", "Country of origin (ISO)", "VARCHAR"),
        ("asylum-applications", "applied", "BIGINT"),
        ("asylum-applications", "Authority", "VARCHAR"),
        ("asylum-applications", "Cases / Persons", "VARCHAR"),
        ("asylum-decisions", "Total decisions", "BIGINT"),
        ("asylum-decisions", "Stage of procedure", "VARCHAR"),
        ("solutions", "Resettlement arrivals", "BIGINT"),
        ("demographics", "Female 0 - 4", "BIGINT"),
        ("demographics", "Total", "BIGINT"),
        ("countries", "id", "INTEGER"),
        ("countries", "0", "INTEGER"),
        ("countries", "iso", "VARCHAR"),
        ("footnotes", "Year", "VARCHAR"),
        ("footnotes", "Footnote", "VARCHAR"),
        # a column the rule does not name stays text, as does a count column of
        # another table
        ("population", "A column from a later release", "VARCHAR"),
        ("population", "applied", "VARCHAR"),
        ("solutions", "Total", "VARCHAR"),
    ],
)
def test_column_type(table, name, sql):
    assert m.column_type(table, name) == sql


def test_every_named_count_column_is_in_the_raw_headings():
    # the rule names columns by the exact heading of the source, misspelling included
    assert "Returned IDPss" in m.COUNTS["population"]
    assert "Returned IDPss" in m.COUNTS["solutions"]
    assert "Returned IDPs" not in m.COUNTS["population"]


def _csv(tmp_path, table, text):
    f = tmp_path / f"{table}.csv"
    f.write_text(text, encoding="utf-8")
    con = duckdb.connect()
    return con.sql(m.select_sql(con, table, f))


SOL = (
    'Year,"Country of origin","Country of origin (ISO)","Country of asylum",'
    '"Country of asylum (ISO)","Returned refugees","Resettlement arrivals",'
    'Naturalisation,"Returned IDPss"\n'
)


def test_counts_are_typed_dash_is_null_and_text_is_kept(tmp_path):
    rel = _csv(tmp_path, "solutions", SOL + '1959,"Unknown ",UNK,Canada,CAN,-,17,-,0\n')
    row = dict(zip(rel.columns, rel.fetchone(), strict=True))
    assert row["Year"] == 1959
    assert row["Resettlement arrivals"] == 17 and row["Returned IDPss"] == 0
    assert row["Returned refugees"] is None and row["Naturalisation"] is None
    # the trailing space of the source's name is kept
    assert row["Country of origin"] == "Unknown "
    assert rel.columns == [
        "Year", "Country of origin", "Country of origin (ISO)", "Country of asylum",
        "Country of asylum (ISO)", "Returned refugees", "Resettlement arrivals",
        "Naturalisation", "Returned IDPss",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("1959,A,AAA,B,BBB,-,17.5,-,-\n", "Resettlement arrivals is not a count or -: 17.5"),
        ("1959,A,AAA,B,BBB,-,-5,-,-\n", "Resettlement arrivals is not a count or -: -5"),
        ('1959,A,AAA,B,BBB,-,"1,200",-,-\n', "Resettlement arrivals is not a count or -: 1,200"),
        ("1959,A,AAA,B,BBB,n/a,5,-,-\n", "Returned refugees is not a count or -: n/a"),
        ("59,A,AAA,B,BBB,-,5,-,-\n", "Year is not a year: 59"),
        ("1959-01,A,AAA,B,BBB,-,5,-,-\n", "Year is not a year: 1959-01"),
    ],
)
def test_a_value_that_does_not_fit_stops_the_run(tmp_path, line, message):
    with pytest.raises(duckdb.Error, match=message):
        _csv(tmp_path, "solutions", SOL + line).fetchall()


def test_an_empty_count_stops_the_run(tmp_path):
    with pytest.raises(duckdb.Error, match="Naturalisation is empty"):
        _csv(tmp_path, "solutions", SOL + "1959,A,AAA,B,BBB,-,5,,-\n").fetchall()


def test_footnote_year_ranges_stay_text(tmp_path):
    text = (
        'Footnote,Year,"Country of origin (ISO)","Country of asylum (ISO)","Population type"\n'
        '"A note, with a comma.",2018 - 2025,,SSD,"REF,IDP"\n'
    )
    rel = _csv(tmp_path, "footnotes", text)
    assert rel.fetchone() == ("A note, with a comma.", "2018 - 2025", None, "SSD", "REF,IDP")


def test_countries_are_typed_and_nulls_and_empty_strings_kept(tmp_path):
    items = [
        {"0": 1, "id": 11, "code": "AUL", "iso": "AUS", "name": "Australia", "nameFr": ""},
        {"0": 1, "id": 290, "code": "CRB", "iso": None, "name": "CRB", "nameFr": None},
    ]
    p = tmp_path / "countries.json"
    p.write_text(json.dumps({"items": items}), encoding="utf-8")
    con = duckdb.connect()
    rel = con.sql(m.countries_sql(con, p, tmp_path))
    assert rel.columns == ["0", "id", "code", "iso", "name", "nameFr"]
    assert rel.fetchall() == [
        (1, 11, "AUL", "AUS", "Australia", ""),
        (1, 290, "CRB", None, "CRB", None),
    ]
    assert m.column_type("countries", "id") == "INTEGER"


def test_countries_with_a_text_id_stop_the_run(tmp_path):
    p = tmp_path / "countries.json"
    p.write_text(json.dumps({"items": [{"0": 1, "id": "x1", "code": "A"}]}), encoding="utf-8")
    con = duckdb.connect()
    with pytest.raises(duckdb.Error, match="id is not an integer: x1"):
        con.sql(m.countries_sql(con, p, tmp_path)).fetchall()


def test_countries_must_share_one_set_of_keys(tmp_path):
    p = tmp_path / "countries.json"
    p.write_text(json.dumps({"items": [{"id": 1}, {"id": 2, "code": "B"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="keys"):
        m.countries_sql(duckdb.connect(), p, tmp_path)


def test_names_that_clash_in_duckdb_stop_the_run():
    with pytest.raises(ValueError, match="Total"):
        m.check_names("demographics", ["Year", "Total", "total"])
    m.check_names("demographics", ["Year", "Female total", "Total"])
