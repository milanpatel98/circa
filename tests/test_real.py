"""The same checks on 100 real hospital patients (MIMIC-IV Demo on FHIR), plus the hospital-specific meanings."""

import pytest

from circa import store as _store

pytestmark = pytest.mark.skipif(not _store.REAL_CHARTS.exists(), reason="run `circa --data real ingest mimic/fhir` first")

from circa import bench, gold, store
from circa.engine import Engine
from circa.verify import check


@pytest.fixture(scope="module")
def charts():
    return store.load_charts(store.REAL_CHARTS)


@pytest.fixture(scope="module")
def engine():
    return Engine(store.load_json(store.REAL_LEXICON))


@pytest.fixture(scope="module")
def questions():
    return bench.load_questions(bench.BENCH / "real-questions.jsonl")


def test_cohort_is_100_real_hospital_patients(charts):
    assert len(charts) == 100
    assert all(c["source"] == "hospital" and c["name"].startswith("Patient ") for c in charts)
    assert sum(len(c["records"]) for c in charts) > 100_000


def test_every_dev_question_is_answered_correctly(charts, engine, questions):
    res = bench.evaluate(engine, charts, [q for q in questions if q["split"] == "dev"])
    assert res["by_split"]["dev"]["accuracy"] == 1.0, res["failures"][:5]


def test_heldout_phrasings_stay_above_95_percent(charts, engine, questions):
    res = bench.evaluate(engine, charts, [q for q in questions if q["split"] == "heldout"])
    assert res["by_split"]["heldout"]["accuracy"] >= 0.95
    assert res["by_split"]["heldout"]["unverified"] == 0


def test_every_answer_passes_the_checker(charts, engine, questions):
    by_id = {c["id"]: c for c in charts}
    for q in questions[::5]:
        chart = by_id[q["patient"]]
        ans = engine.ask(chart, q["question"])
        assert check(chart, ans, q["question"])["ok"], (q["question"], ans["text"])


def test_current_medications_mean_the_most_recent_stay(charts, engine):
    chart = max(charts, key=lambda c: sum(r["type"] == "Encounter" and r["cls"] == "IMP" for r in c["records"]))
    ans = engine.ask(chart, "what medications is the patient on")
    assert "most recent hospital stay" in ans["text"]
    cited = {i for cl in ans["claims"] for i in cl["cites"]}
    meds = {r["id"]: r for r in chart["records"] if r["type"] == "MedicationRequest"}
    last = gold._last_enc(meds.values())
    assert cited & meds.keys() and all(meds[i]["enc"] == last for i in cited & meds.keys())


def test_diagnoses_are_recorded_not_active(charts, engine):
    chart = next(c for c in charts if any(r["type"] == "Condition" and "hypertension" in r["name"].lower() for r in c["records"]))
    ans = engine.ask(chart, "does the patient have high blood pressure")
    assert ans["text"].startswith("Yes.") and "recorded at the hospital stay" in ans["text"]


def test_every_kind_of_clinical_record_is_read(charts):
    types = {r["type"] for c in charts for r in c["records"]}
    assert types >= {"Encounter", "Condition", "Observation", "Procedure", "MedicationRequest",
                     "MedicationAdministration", "MedicationDispense", "MedicationStatement"}
    cats = {r.get("cat") for c in charts for r in c["records"] if r["type"] == "Observation"}
    assert cats >= {"lab", "vital", "icu", "output", "micro", "ed"}
    assert {r["cls"] for c in charts for r in c["records"] if r["type"] == "Encounter"} == {"IMP", "EMER", "ICU"}
    assert sum(len(c["records"]) for c in charts) > 850_000


def test_icu_blood_pressure_is_one_reading(charts, engine):
    chart = next(c for c in charts if any(r["code"] == "220179" for r in c["records"]))
    bp = [r for r in chart["records"] if r["code"] == "220179" and "parts" in r]
    assert bp and all([p[0] for p in r["parts"]] == ["8480-6", "8462-4"] for r in bp)
    ans = engine.ask(chart, "what was the last blood pressure")
    assert ans["status"] == "answered" and "/" in ans["text"]


def test_last_visit_is_an_admission_or_ed_visit_not_an_icu_transfer(charts, engine):
    for chart in charts[:20]:
        ans = engine.ask(chart, "when was the patient last seen")
        rec = next(r for r in chart["records"] if r["id"] == ans["result"]["id"])
        assert rec["cls"] != "ICU"
