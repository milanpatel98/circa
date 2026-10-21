"""Write the website's data: the vocabulary, a handful of demo patients with their original FHIR resources,
the benchmark results, and the expected answers the JavaScript port is tested against."""

from __future__ import annotations

import json
from pathlib import Path

from . import bench, store
from .engine import Engine
from .fhir import ingest_bundle, load_bundle

WEB = store.ROOT / "web"
OUT = WEB / "public" / "data"
DEMO = ["53eac38d", "18086428", "77468e23", "b4af4b17", "7f4ca04b", "e7da4bac"]

SUGGEST = {
    "default": ["What was {poss} last A1c?", "How has {poss} blood pressure changed?", "What medications is {subj} on?", "Does {subj} have diabetes?",
                "Any allergies?", "When was {poss} last flu shot?", "ER visits in the past year?", "Should we increase {poss} lisinopril?"],
}


def _pron(sex):
    return bench.pronouns(sex)


def export(charts: list[dict], lex: dict, synthea: Path = store.ROOT / "synthea" / "fhir") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "p").mkdir(exist_ok=True)
    store.save_json(lex, OUT / "lexicon.json")
    engine = Engine(lex)
    demo = [next(c for c in charts if c["id"].startswith(p)) for p in DEMO]

    raw_by_id: dict[str, dict] = {}
    if synthea.exists():
        wanted = {c["id"] for c in demo}
        for f in sorted(synthea.glob("*.json")):
            if any(f.name.endswith(f"{pid}.json") for pid in wanted):
                chart, raw = ingest_bundle(load_bundle(f))
                raw_by_id[chart["id"]] = raw

    listing = []
    for c in demo:
        path = OUT / "p" / f"{c['id']}.json"
        raw = raw_by_id.get(c["id"])
        if raw is None and path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))["raw"]
        store.save_json({"chart": c, "raw": raw or {}}, path)
        p = _pron(c["sex"])
        active = sorted({r["name"] for r in c["records"] if r["type"] == "Condition" and r["status"] == "active"})
        meds = len({r["code"] for r in c["records"] if r["type"] == "MedicationRequest" and r["status"] == "active"})
        y0 = int(c["asOf"][:4]) - 11
        spark = [sum(1 for r in c["records"] if int(r["date"][:4]) == y) for y in range(y0, y0 + 12)]
        listing.append({"id": c["id"], "name": c["name"], "sex": c["sex"], "birthDate": c["birthDate"], "records": len(c["records"]), "spark": spark,
                        "conditions": len(active), "meds": meds,
                        "suggest": [bench.fill(t, p) for t in SUGGEST["default"]]})
    store.save_json({"asOf": charts[0]["asOf"], "patients": listing, "cohort": len(charts),
                     "recordCount": sum(len(c["records"]) for c in charts)}, OUT / "patients.json")

    # results for the page
    res = {}
    for name in ("circa", "rag5", "rag20"):
        f = store.ROOT / "artifacts" / f"bench-{name}.json"
        if f.exists():
            r = json.loads(f.read_text())
            res[name] = {"by_split": r["by_split"], "by_category": {k: {s: v[s]["accuracy"] for s in v} for k, v in r["by_category"].items()}}
    first = store.ROOT / "artifacts" / "heldout-first-run.json"
    if first.exists():
        res["first_run_heldout"] = json.loads(first.read_text())["by_split"]["heldout"]
    res["categories"] = bench.CATEGORIES
    res["questions"] = len(bench.load_questions(bench.BENCH / "questions.jsonl"))
    store.save_json(res, OUT / "results.json")

    # what the JavaScript engine must reproduce, question by question
    qs = bench.load_questions(bench.BENCH / "questions.jsonl")
    expected = []
    for c in demo:
        asks = [q["question"] for q in qs if q["patient"] == c["id"]] + [l for p in listing if p["id"] == c["id"] for l in p["suggest"]]
        for q in asks:
            a = engine.ask(c, q)
            expected.append({"patient": c["id"], "question": q, "answer": {k: a[k] for k in ("status", "intent", "concept", "window", "claims", "result", "text")}})
    (WEB / "test").mkdir(parents=True, exist_ok=True)
    (WEB / "test" / "expected.json").write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")
    print(f"{len(demo)} demo patients, {len(expected)} expected answers -> {OUT}")
