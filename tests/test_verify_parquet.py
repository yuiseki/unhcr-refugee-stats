import importlib.util
import sys
import zipfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vf = _load("verify_pq", "02_verify.py")
ex = vf.export

CSV = (
    'Year,"Country of origin","Country of origin (ISO)","Country of asylum",'
    '"Country of asylum (ISO)","Returned refugees","Resettlement arrivals",'
    'Naturalisation,"Returned IDPss"\n'
    '1959,"Unknown ",UNK,Canada,CAN,-,17,-,-\n'
    "1960,Albania,ALB,Canada,CAN,0,5,10,-\n"
)


def _digests(tmp_path, sql_edit=None):
    z = tmp_path / "solutions.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("solutions.csv", CSV)
    (tmp_path / "solutions.csv").write_text(CSV, encoding="utf-8")
    con = duckdb.connect()
    sql = ex.select_sql(con, "solutions", tmp_path / "solutions.csv")
    if sql_edit:
        sql = f"select * replace ({sql_edit}) from ({sql})"
    p = tmp_path / "solutions.parquet"
    con.execute(f"copy ({sql}) to '{p}' (format parquet)")
    types = {r[0]: r[1] for r in con.sql(f"describe select * from '{p}'").fetchall()}
    return vf.raw_csv_digest(z, "solutions.csv"), vf.parquet_digest(con, p, types, True)


def test_digest_of_an_unchanged_table_equals_the_raw_one(tmp_path):
    (header, n, raw), (n_pq, pq) = _digests(tmp_path)
    assert header[-1] == "Returned IDPss"
    assert (n, raw) == (n_pq, pq) and n == 2


def test_digest_catches_a_dash_read_as_zero(tmp_path):
    (_, _, raw), (_, pq) = _digests(tmp_path, '0::bigint as "Returned IDPss"')
    assert raw != pq


def test_digest_catches_a_trimmed_name(tmp_path):
    (_, _, raw), (_, pq) = _digests(tmp_path, 'trim("Country of origin") as "Country of origin"')
    assert raw != pq
