#!/usr/bin/env python3
"""Push the card, UNHCR's own raw files and their Parquet to the Hugging Face Hub.

Only UNHCR's own series go up: data/raw/<version>/unhcr/ and the Parquet made
from it. data/raw/<version>/third-party/ (IDMC, UNRWA) never does: UNHCR's
Terms of Use for Datasets, item 6, say that data provided by third parties may
not be redistributed without the consent of the original provider.

Refuses to run if the card does not declare every Parquet file as a subset,
or if a raw file's sha256 differs from its MANIFEST.json.

    uv run python src/publish.py             # dry run
    uv run python src/publish.py --push
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPO = "yuiseki/unhcr-refugee-stats"
PUBLISHED_RAW = "unhcr/"  # the folder of each version that goes up; third-party/ does not


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def subset_entry(version: str, table: str) -> str:
    return f"- config_name: '{version}.{table}'\n  data_files: parquet/{version}/{table}.parquet\n"


def files_to_publish(data: Path = DATA) -> list[str]:
    card = (data / "README.md").read_text(encoding="utf-8")
    files = ["README.md", "LICENSE", "provenance.yaml"]
    versions = sorted(p.parent.name for p in (data / "raw").glob("*/MANIFEST.json"))
    if not versions:
        raise SystemExit("no data/raw/<version>/MANIFEST.json")
    for version in versions:
        d = data / "raw" / version
        manifest = json.loads((d / "MANIFEST.json").read_text())
        files.append(f"raw/{version}/MANIFEST.json")
        for name, m in manifest.items():
            if not name.startswith(PUBLISHED_RAW):
                continue
            if sha256(d / name) != m["sha256"]:
                raise SystemExit(f"raw/{version}/{name} is not the file in its manifest")
            files.append(f"raw/{version}/{name}")
        parquet = sorted((data / "parquet" / version).glob("*.parquet"))
        if not parquet:
            raise SystemExit(f"no Parquet for {version}; run scripts/03_export_parquet.py")
        for p in parquet:
            if subset_entry(version, p.stem) not in card:
                raise SystemExit(f"the card does not declare the subset {version}.{p.stem}")
            files.append(f"parquet/{version}/{p.name}")
    leaked = [f for f in files if "third-party" in f]
    if leaked:
        raise SystemExit(f"third-party files would be published: {leaked}")
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    files = files_to_publish()
    total = 0
    for f in files:
        size = (DATA / f).stat().st_size
        total += size
        print(f"  {size:>12,}  {f}")
    print(f"{a.repo}\n  {len(files)} files, {total:,} bytes ({total / 1e6:.1f} MB)")
    if not a.push:
        print("\ndry run. pass --push to upload")
        return 0

    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(a.repo, repo_type="dataset", exist_ok=True, private=False)
    api.upload_folder(
        folder_path=str(DATA), repo_id=a.repo, repo_type="dataset", allow_patterns=files
    )
    print(f"\npushed to https://huggingface.co/datasets/{a.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
