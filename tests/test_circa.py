import copy
import json

import pytest

from circa import bench, gold, store
from circa.engine import Engine
from circa.fhir import ingest_bundle
from circa.lexicon import build, ingredients
from circa.llm import ClaudeAnswerer
from circa.parse import Parser, minus_months
from circa.rag import RagAnswerer
from circa.verify import check

AS_OF = "2026-10-20"


@pytest.fixture(scope="module")
def charts():
    return store.load_charts()


@pytest.fixture(scope="module")
def lex():
    return store.load_json(store.LEXICON)


@pytest.fixture(scope="module")
def engine(lex):
    return Engine(lex)


@pytest.fixture(scope="module")
def questions():
    return bench.load_questions(bench.BENCH / "questions.jsonl")


# ---- ingest ----------------------------------------------------------------------------------

def bundle():
    pid = "p1"
    def entry(r):
        return {"resource": r}
    return {"resourceType": "Bundle", "entry": [
        entry({"resourceType": "Patient", "id": pid, "gender": "female", "birthDate": "1960-05-02",
               "name": [{"given": ["Ada123"], "family": "Lovelace456"}]}),
        entry({"resourceType": "Medication", "id": "m1", "code": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "314076",
                                                                               "display": "lisinopril 10 MG Oral Tablet"}]}}),
        entry({"resourceType": "MedicationRequest", "id": "mr1", "status": "active", "authoredOn": "2020-01-05T10:00:00-07:00",
               "medicationReference": {"reference": "urn:uuid:m1"}, "reasonReference": [{"display": "Essential hypertension (disorder)"}]}),
        entry({"resourceType": "Condition", "id": "c1", "clinicalStatus": {"coding": [{"code": "active"}]},
               "code": {"coding": [{"system": "http://snomed.info/sct", "code": "59621000", "display": "Essential hypertension (disorder)"}]},
               "onsetDateTime": "2019-12-01T09:00:00-07:00"}),
        entry({"resourceType": "Condition", "id": "c2", "clinicalStatus": {"coding": [{"code": "active"}]},
               "code": {"coding": [{"system": "http://snomed.info/sct", "code": "160903007", "display": "Full-time employment (finding)"}]},
               "onsetDateTime": "2019-12-01T09:00:00-07:00"}),
        entry({"resourceType": "Observation", "id": "o1", "category": [{"coding": [{"code": "vital-signs"}]}],
               "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel"}]},
               "effectiveDateTime": "2026-01-03T09:00:00-07:00",
               "component": [{"code": {"coding": [{"code": "8462-4", "display": "Diastolic"}]}, "valueQuantity": {"value": 82, "unit": "mm[Hg]"}},
                             {"code": {"coding": [{"code": "8480-6", "display": "Systolic"}]}, "valueQuantity": {"value": 131, "unit": "mm[Hg]"}}]}),
        entry({"resourceType": "Observation", "id": "o2", "category": [{"coding": [{"code": "survey"}]}],
               "code": {"coding": [{"system": "http://loinc.org", "code": "44249-1", "display": "PHQ-9"}]}, "effectiveDateTime": "2026-01-03",
               "valueQuantity": {"value": 3}}),
        entry({"resourceType": "Claim", "id": "x1"}),
    ]}


def test_ingest_keeps_clinical_records_with_their_ids():
    chart, raw = ingest_bundle(bundle())
    assert chart["name"] == "Ada Lovelace"
    ids = {r["id"] for r in chart["records"]}
    assert ids == {"mr1", "c1", "o1"}  # social finding, survey and billing dropped
    med = next(r for r in chart["records"] if r["id"] == "mr1")
    assert med["name"] == "lisinopril 10 MG Oral Tablet" and med["reason"] == "Essential hypertension"
    bp = next(r for r in chart["records"] if r["id"] == "o1")
    assert bp["date"] == "2026-01-03" and bp["at"] == "2026-01-03T16:00:00Z" and bp["parts"][0][3] == "mmHg"
    assert set(raw) == ids and "text" not in raw["c1"]


def test_ingredient_names_ignore_dose_forms():
    assert ingredients("24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet") == ["metformin"]
    assert ingredients("NDA020800 0.3 ML Epinephrine 1 MG/ML Auto-Injector") == ["epinephrine"]
    assert ingredients("Acetaminophen 325 MG / Oxycodone Hydrochloride 5 MG Oral Tablet [Percocet]") == ["acetaminophen", "oxycodone"]
    assert ingredients("{28 (norethindrone 0.35 MG Oral Tablet) } Pack [Errin 28 Day]") == ["norethindrone"]


def test_vocabulary_is_rebuilt_identically(charts, lex):
    assert build(charts) == lex


# ---- parsing ---------------------------------------------------------------------------------

@pytest.mark.parametrize("q,intent,concept", [
    ("what was her last a1c", "latest_value", "obs:a1c"),
    ("is he still on a statin?", "on_med", "medclass:statin"),
    ("does she have high blood pressure", "has_condition", "cond:hypertension"),
    ("any ER visits in the past year", "er_visits", None),
    ("How has her blood pressure changed?", "trend", "obs:bp"),
    ("is she allergic to penicillin", "allergy_check", "allergy:7984"),
    ("Is there allergic rhinitis on her record?", "has_condition", "cond:allergic_rhinitis"),
    ("Does she have sleep apnea?", "has_condition", "cond:sleep_apnea"),
    ("what are his medicaitons", "med_list", None),
    ("covid vaccine?", "vaccine_last", "vax:covid_vax"),
    ("has she had covid", "has_condition", "cond:covid"),
    ("should we increase her lisinopril", "advice", None),
    ("any family history of diabetes", "unsupported", None),
    ("how has she been doing", "unsupported", None),
])
def test_parser(lex, q, intent, concept):
    got = Parser(lex).parse(q, AS_OF)
    assert (got["intent"], got["concept"]) == (intent, concept)


def test_time_frames(lex):
    p = Parser(lex)
    assert p.parse("a1c in 2021", AS_OF)["window"] == {"start": "2021-01-01", "end": "2021-12-31", "label": "in 2021"}
    assert p.parse("ER visits in the past year", AS_OF)["window"]["start"] == "2025-10-20"
    assert p.parse("weight over the past 2 years", AS_OF)["window"]["start"] == "2024-10-20"
    assert minus_months("2024-03-31", 1) == "2024-02-29"


# ---- answers ---------------------------------------------------------------------------------

def test_every_dev_question_is_answered_correctly(charts, engine, questions):
    res = bench.evaluate(engine, charts, [q for q in questions if q["split"] == "dev"])
    assert res["by_split"]["dev"]["accuracy"] == 1.0, res["failures"][:5]


def test_heldout_phrasings_stay_above_95_percent(charts, engine, questions):
    res = bench.evaluate(engine, charts, [q for q in questions if q["split"] == "heldout"])
    assert res["by_split"]["heldout"]["accuracy"] >= 0.95


def test_every_answer_passes_the_checker(charts, engine, questions):
    by_id = {c["id"]: c for c in charts}
    for q in questions[::3]:
        chart = by_id[q["patient"]]
        ans = engine.ask(chart, q["question"])
        assert check(chart, ans, q["question"])["ok"], (q["question"], ans["text"])


def test_refuses_rather_than_guesses(charts, engine):
    chart = charts[0]
    assert engine.ask(chart, "Should we double her insulin?")["status"] == "advice"
    assert engine.ask(chart, "What did the MRI show?")["status"] == "unsupported"
    nf = engine.ask(dict(chart, records=[]), "latest a1c")
    assert nf["status"] == "not_found" and nf["claims"][0]["cites"] == []


def test_latest_means_newest_not_most_similar(charts, engine, lex):
    """The failure the benchmark is about: retrieval returns similar records, not the newest one."""
    chart = next(c for c in charts if sum(r["code"] == "4548-4" for r in c["records"]) >= 8)
    codes = next(c["codes"] for c in lex["concepts"] if c["key"] == "obs:a1c")
    want = gold.latest(chart, codes)
    assert engine.ask(chart, "latest a1c")["result"]["id"] == want


def test_circa_beats_retrieval_by_a_wide_margin(charts, lex, engine, questions):
    sample = [q for q in questions if q["split"] == "dev"]
    ours = bench.evaluate(engine, charts, sample)["by_split"]["dev"]["accuracy"]
    rag = bench.evaluate(RagAnswerer(lex, 5), charts, sample)["by_split"]["dev"]["accuracy"]
    assert ours - rag > 0.2


# ---- checker ---------------------------------------------------------------------------------

def test_checker_catches_changed_numbers_dates_and_ids(charts, engine):
    chart = next(c for c in charts if any(r["code"] == "4548-4" for r in c["records"]))
    ans = engine.ask(chart, "latest a1c")
    assert check(chart, ans)["ok"]
    value = ans["result"]["value"].rstrip("%").split()[0]
    bad = copy.deepcopy(ans)
    bad["claims"][0]["text"] = bad["claims"][0]["text"].replace(value, "9.9" if value != "9.9" else "8.8", 1)
    assert any(p["kind"] == "number not in cited records" for p in check(chart, bad)["problems"])
    bad = copy.deepcopy(ans)
    bad["claims"][0]["text"] = bad["claims"][0]["text"].replace(bad["claims"][0]["text"][-13:-1], "Jan 1, 2001")
    assert any(p["kind"] == "date not in cited records" for p in check(chart, bad)["problems"])
    bad = copy.deepcopy(ans)
    bad["claims"][0]["cites"] = ["made-up-id"]
    assert any(p["kind"] == "unknown citation" for p in check(chart, bad)["problems"])
    bad = copy.deepcopy(ans)
    bad["claims"][0]["cites"] = []
    assert any(p["kind"] == "uncited claim" for p in check(chart, bad)["problems"])


# ---- benchmark -------------------------------------------------------------------------------

def test_committed_questions_match_a_fresh_build(charts, lex, questions):
    heldout = store.load_json(bench.BENCH / "heldout.json")
    assert bench.build(charts, lex, heldout) == questions


def test_claude_answerer_loop_with_a_fake_model(charts, questions):
    chart = charts[0]
    calls = []

    def fake(body):
        calls.append(body)
        if len(calls) == 1:
            return {"content": [{"type": "tool_use", "id": "t1", "name": "patient", "input": {}}]}
        return {"content": [{"type": "tool_use", "id": "t2", "name": "answer", "input": {
            "status": "answered", "intent": "age", "claims": [{"text": "Age known.", "cites": [chart["id"]]}],
            "result": {"years": gold.age(chart)}}}]}

    ans = ClaudeAnswerer(transport=fake).ask(chart, "how old is she")
    assert bench.grade(ans, {"intent": "age", "years": gold.age(chart)})
    tool_result = json.loads(calls[1]["messages"][2]["content"][0]["content"])
    assert tool_result["birthDate"] == chart["birthDate"]
