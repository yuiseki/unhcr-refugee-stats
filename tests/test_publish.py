import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "publish", Path(__file__).parents[1] / "src" / "publish.py"
)
pub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pub)

V = "2026-10-04"


def _data(tmp_path, card_tables=("population",)):
    raw = tmp_path / "raw" / V
    for rel, body in {"unhcr/population.zip": b"p", "third-party/idmc.zip": b"i"}.items():
        (raw / rel).parent.mkdir(parents=True, exist_ok=True)
        (raw / rel).write_bytes(body)
    manifest = {
        "unhcr/population.zip": {"sha256": hashlib.sha256(b"p").hexdigest()},
        "third-party/idmc.zip": {"sha256": hashlib.sha256(b"i").hexdigest()},
    }
    (raw / "MANIFEST.json").write_text(json.dumps(manifest))
    (tmp_path / "parquet" / V).mkdir(parents=True)
    (tmp_path / "parquet" / V / "population.parquet").write_bytes(b"pq")
    card = "configs:\n" + "".join(pub.subset_entry(V, t) for t in card_tables)
    (tmp_path / "README.md").write_text(card)
    return tmp_path


def test_third_party_is_left_out(tmp_path):
    files = pub.files_to_publish(_data(tmp_path))
    assert f"raw/{V}/unhcr/population.zip" in files
    assert f"parquet/{V}/population.parquet" in files
    assert not [f for f in files if "third-party" in f or "idmc" in f]


def test_refuses_an_undeclared_subset(tmp_path):
    with pytest.raises(SystemExit, match=f"{V}.population"):
        pub.files_to_publish(_data(tmp_path, card_tables=()))


def test_refuses_a_raw_file_that_is_not_in_its_manifest(tmp_path):
    d = _data(tmp_path)
    (d / "raw" / V / "unhcr" / "population.zip").write_bytes(b"changed")
    with pytest.raises(SystemExit, match="not the file in its manifest"):
        pub.files_to_publish(d)


def test_subset_entry_is_version_dot_table():
    assert pub.subset_entry(V, "asylum-decisions") == (
        f"- config_name: '{V}.asylum-decisions'\n"
        f"  data_files: parquet/{V}/asylum-decisions.parquet\n"
    )
