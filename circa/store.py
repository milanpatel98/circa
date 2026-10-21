"""Reading and writing the cohort: data/charts.jsonl.gz (one chart per line) and data/lexicon.json."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CHARTS = DATA / "charts.jsonl.gz"
LEXICON = DATA / "lexicon.json"


def save_charts(charts: list[dict], path: Path = CHARTS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the file byte-identical across runs
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
        for c in charts:
            f.write((json.dumps(c, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8"))


def load_charts(path: Path = CHARTS) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def save_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
