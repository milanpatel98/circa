"""Write the website's data: the vocabulary, a handful of real demo patients with their original FHIR resources,
the benchmark results on real and synthetic patients, and the expected answers the JavaScript port is tested against."""

from __future__ import annotations

import json
from pathlib import Path

from . import bench, gold, store
from .engine import Engine

WEB = store.ROOT / "web"
OUT = WEB / "public" / "data"
MIMIC = store.ROOT / "mimic" / "fhir"  # not committed; see README for where to get it
DEMO = ["27980ad8", "4c9069e4", "bc2a74ce", "3886cafb", "c4c29979", "b410dd44"]

SUGGEST = ["What was {poss} last A1c?", "How has {poss} blood pressure changed?", "What medications is {subj} on?", "Does {subj} have diabetes?",
           "Any ER visits in the past year?", "When was {subj} last seen?", "Should we increase {poss} insulin?",
           "How has {poss} creatinine changed?", "How has {poss} hemoglobin changed?", "What was {poss} last potassium?", "Is {subj} on a blood thinner?",
           "Is {subj} on insulin?", "What are {poss} active problems?", "Does {subj} have heart failure?", "Does {subj} have kidney disease?",
           "How many ER visits in the past year?", "How old is {subj}?"]


def _results(prefix: str, qfile: str) -> dict:
    out = {}
    for name in ("circa", "rag5", "rag20"):
        f = store.ROOT / "artifacts" / f"{prefix}-{name}.json"
        if f.exists():
            r = json.loads(f.read_text())
            out[name] = {"by_split": r["by_split"], "by_category": {k: {s: v[s]["accuracy"] for s in v} for k, v in r["by_category"].items() if v["heldout"]["n"]}}
    out["questions"] = len(bench.load_questions(bench.BENCH / qfile))
    return out


def export() -> None:
    charts = store.load_charts(store.REAL_CHARTS)
    lex = store.load_json(store.REAL_LEXICON)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "p").mkdir(exist_ok=True)
    for old in (OUT / "p").glob("*.json"):
        if not any(old.name.startswith(d) for d in DEMO):
            old.unlink()
    store.save_json(lex, OUT / "lexicon.json")
    engine = Engine(lex)
    demo = [next(c for c in charts if c["id"].startswith(p)) for p in DEMO]

    raw_all: dict[str, dict] = {}
    if MIMIC.exists():
        from .mimic import ingest
        _, raw_all = ingest(MIMIC)

    listing = []
    for c in demo:
        path = OUT / "p" / f"{c['id']}.json"
        ids = {r["id"] for r in c["records"]}
        raw = {k: v for k, v in raw_all.items() if k in ids} if raw_all else None
        if raw is None and path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))["raw"]
        store.save_json({"chart": c, "raw": raw or {}}, path)
        p = bench.pronouns(c["sex"])
        y0 = int(c["asOf"][:4]) - 11
        spark = [sum(1 for r in c["records"] if int(r["date"][:4]) == y) for y in range(y0, y0 + 12)]
        listing.append({"id": c["id"], "name": c["name"], "sex": c["sex"], "birthDate": c["birthDate"], "asOf": c["asOf"],
                        "records": len(c["records"]), "spark": spark,
                        "conditions": len(gold.active_problems(c)), "meds": len(gold.active_meds(c)),
                        "stays": sum(1 for r in c["records"] if r["type"] == "Encounter" and r["cls"] == "IMP"),
                        "suggest": [bench.fill(t, p) for t in SUGGEST]})
    store.save_json({"source": "MIMIC-IV Clinical Database Demo on FHIR", "patients": listing, "cohort": len(charts),
                     "recordCount": sum(len(c["records"]) for c in charts)}, OUT / "patients.json")

    res = {"real": _results("real-bench", "real-questions.jsonl"), "synthetic": _results("bench", "questions.jsonl"),
           "categories": bench.CATEGORIES}
    first = store.ROOT / "artifacts" / "heldout-first-run.json"
    if first.exists():
        res["synthetic"]["first_run_heldout"] = json.loads(first.read_text())["by_split"]["heldout"]
    store.save_json(res, OUT / "results.json")

    # what the JavaScript engine must reproduce, question by question
    qs = bench.load_questions(bench.BENCH / "real-questions.jsonl")
    expected = []
    for c in demo:
        asks = [q["question"] for q in qs if q["patient"] == c["id"]] + [l for p in listing if p["id"] == c["id"] for l in p["suggest"]]
        for q in asks:
            a = engine.ask(c, q)
            expected.append({"patient": c["id"], "question": q, "answer": {k: a[k] for k in ("status", "intent", "concept", "window", "claims", "result", "text")}})
    (WEB / "test").mkdir(parents=True, exist_ok=True)
    (WEB / "test" / "expected.json").write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")
    print(f"{len(demo)} real demo patients, {len(expected)} expected answers -> {OUT}")
