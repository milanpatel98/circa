"""circa: ask questions of synthetic FHIR patient records, and measure how well it answers.

  circa ingest [synthea/fhir]     build data/charts.jsonl.gz and data/lexicon.json from Synthea bundles
  circa patients                  list patients
  circa ask PATIENT "question"    answer one question (PATIENT: id prefix or name)
  circa questions                 build bench/questions.jsonl
  circa bench [--answerer ...]    score an answerer: circa, rag5, rag20 or claude
  circa export                    write the website's data
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import bench, store
from .engine import Engine
from .verify import check


def _answerer(name: str, lex: dict):
    if name == "circa":
        return Engine(lex)
    if name.startswith("rag"):
        from .rag import RagAnswerer
        return RagAnswerer(lex, int(name[3:] or 5))
    if name == "claude":
        from .llm import ClaudeAnswerer
        return ClaudeAnswerer()
    raise SystemExit(f"unknown answerer {name}")


def find(charts: list[dict], who: str) -> dict:
    w = who.lower()
    for c in charts:
        if c["id"].startswith(w) or c["name"].lower() == w:
            return c
    matches = [c for c in charts if w in c["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(f"no single patient matches {who!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="circa", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap.add_argument("--data", choices=["synthetic", "real"], default="synthetic",
                    help="synthetic: Synthea patients (default); real: MIMIC-IV demo hospital patients")
    p = sub.add_parser("ingest"); p.add_argument("src", nargs="?", default=None, help="synthea/fhir, or the MIMIC fhir/ folder with --data real")
    sub.add_parser("patients")
    p = sub.add_parser("ask"); p.add_argument("patient"); p.add_argument("question"); p.add_argument("--json", action="store_true")
    sub.add_parser("questions")
    p = sub.add_parser("bench"); p.add_argument("--answerer", default="circa"); p.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    p.add_argument("--limit", type=int, default=0, help="only the first N patients")
    sub.add_parser("export")
    a = ap.parse_args(argv)

    real = a.data == "real"
    charts_path = store.REAL_CHARTS if real else store.CHARTS
    lex_path = store.REAL_LEXICON if real else store.LEXICON
    q_path = bench.BENCH / ("real-questions.jsonl" if real else "questions.jsonl")
    prefix = "real-bench" if real else "bench"

    if a.cmd == "ingest" and real:
        from .lexicon import build
        from .mimic import ingest as ingest_mimic
        charts, _ = ingest_mimic(Path(a.src or "mimic/fhir"))
        store.save_charts(charts, store.REAL_CHARTS)
        store.save_json(build(charts), store.REAL_LEXICON)
        print(f"{len(charts)} real patients, {sum(len(c['records']) for c in charts):,} records -> {store.REAL_CHARTS}")
        return 0

    if a.cmd == "ingest":
        from .fhir import ingest_bundle, load_bundle
        from .lexicon import build
        charts = []
        for f in sorted(Path(a.src or "synthea/fhir").glob("*.json")):
            chart, _ = ingest_bundle(load_bundle(f))
            if not chart["deceased"]:
                charts.append(chart)
        charts.sort(key=lambda c: c["id"])
        store.save_charts(charts)
        store.save_json(build(charts), store.LEXICON)
        print(f"{len(charts)} living patients, {sum(len(c['records']) for c in charts):,} records -> {store.CHARTS}")
        return 0

    charts = store.load_charts(charts_path)
    lex = store.load_json(lex_path)

    if a.cmd == "patients":
        for c in charts:
            print(f"{c['id'][:8]}  {c['name']:<28} {c['sex']:<7} born {c['birthDate']}  {len(c['records']):>6} records")
        return 0

    if a.cmd == "ask":
        chart = find(charts, a.patient)
        ans = Engine(lex).ask(chart, a.question)
        ans["check"] = check(chart, ans, a.question)
        if a.json:
            print(json.dumps(ans, indent=2, ensure_ascii=False))
        else:
            print(f"{chart['name']} · {ans['intent']} · {ans['status']}\n")
            for c in ans["claims"]:
                print(f"  {c['text']}" + (f"   [{', '.join(x[:8] for x in c['cites'])}]" if c["cites"] else ""))
            print("\n  checked: " + ("every number and date matches its source" if ans["check"]["ok"] else json.dumps(ans["check"]["problems"])))
        return 0

    if a.cmd == "questions":
        heldout = store.load_json(bench.BENCH / "heldout.json")
        qs = bench.build(charts, lex, heldout)
        bench.save_questions(qs, q_path)
        print(f"{len(qs)} questions over {len(charts)} patients -> {q_path}")
        return 0

    if a.cmd == "bench":
        qs = bench.load_questions(q_path)
        if a.split != "all":
            qs = [q for q in qs if q["split"] == a.split]
        use = charts[: a.limit] if a.limit else charts
        t0 = time.time()
        res = bench.evaluate(_answerer(a.answerer, lex), use, qs)
        res["answerer"] = a.answerer
        res["seconds"] = round(time.time() - t0, 1)
        out = Path("artifacts") / f"{prefix}-{a.answerer}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
        for split, s in res["by_split"].items():
            if s["n"]:
                print(f"{a.answerer:>7} {split:<8} {s['accuracy']:.1%}  ({s['correct']}/{s['n']}, 95% CI {s['ci'][0]:.1%}–{s['ci'][1]:.1%})  "
                      f"wrong answers {s['wrong_answers']}  failed check {s['unverified']}")
        print(f"-> {out}  ({res['seconds']}s)")
        return 0

    if a.cmd == "export":
        from .export import export
        export()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
