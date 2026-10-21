"""The benchmark: questions about every patient, each with an answer key from gold.py.

Every question is asked twice: once in a phrasing written while building the parser ('dev'), and once in a
phrasing written separately, without access to the parser ('held-out', bench/heldout.json). The gap between the
two is how much the parser depends on wording it has seen.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

from . import gold
from .parse import minus_months
from .verify import check

BENCH = Path(__file__).resolve().parent.parent / "bench"

# Phrasings written while building the parser.
DEV = {
    "latest_value": ["What was {poss} last {concept}?", "Latest {concept}?", "What is the patient's most recent {concept}?", "Most recent {concept} for {obj}",
                     "What's {poss} current {concept}?", "Show me {poss} latest {concept} result"],
    "latest_in_year": ["What was {poss} {concept} in {year}?", "{concept} in {year}", "Any {concept} results from {year}?", "What did {poss} {concept} look like in {year}?"],
    "trend": ["How has {poss} {concept} changed over time?", "{concept} trend", "Show me the trend in {poss} {concept}", "Is {poss} {concept} going up or down?",
              "What has {poss} {concept} been over the last few results?"],
    "has_condition": ["Does {subj} have {concept}?", "Any history of {concept}?", "{has} {subj} ever been diagnosed with {concept}?", "Is there {concept} on {poss} record?",
                      "hx of {concept}?"],
    "problem_list": ["What are {poss} active problems?", "Problem list", "What conditions does {subj} have?", "Current diagnoses?"],
    "on_med": ["Is {subj} on {concept}?", "{is} {subj} taking {concept}?", "Is the patient currently on {concept}?", "Does {subj} take {concept}?", "Still on {concept}?"],
    "med_list": ["What medications is {subj} on?", "Current meds?", "List {poss} active medications", "What is {subj} taking right now?"],
    "med_start": ["When did {subj} start {concept}?", "When was {concept} first prescribed?", "How long has {subj} been on {concept}?", "Start date for {concept}?"],
    "allergy_list": ["Does {subj} have any allergies?", "Allergies?", "List {poss} allergies", "What is the patient allergic to?"],
    "allergy_check": ["Is {subj} allergic to {concept}?", "Any {concept} allergy?", "{concept} allergy?", "Does {subj} have an allergy to {concept}?"],
    "vaccine_last": ["When was {poss} last {concept} shot?", "Has {subj} had the {concept} vaccine?", "Last {concept} vaccine?", "Date of {poss} most recent {concept} vaccination"],
    "er_visits": ["How many ER visits in the past year?", "Any emergency visits in the last 12 months?", "ED visits in the past year?",
                  "Has {subj} been to the emergency room in the past 12 months?"],
    "last_visit": ["When was {subj} last seen?", "When was {poss} last visit?", "Last appointment?", "Date of the most recent encounter"],
    "age": ["How old is {subj}?", "Patient age?", "What is {poss} age?"],
}
DEV_UNSUPPORTED = ["What did {poss} last MRI show?", "Any family history of heart disease?", "Who is {poss} primary care doctor?", "What insurance does {subj} have?",
                   "What does {subj} usually eat?", "Does {subj} exercise?", "What did {subj} say about the pain?", "Any genetic test results?"]
DEV_ADVICE = ["Should we increase {poss} lisinopril?", "What dose of metformin should {subj} get?", "Is it safe to start {obj} on a statin?",
              "Should {subj} stop {poss} inhaler?", "What would you prescribe for {poss} blood pressure?", "Can {subj} take ibuprofen?"]

# Natural names to ask about each concept by.
OBS_SURFACE = {
    "a1c": ["a1c", "hba1c", "hemoglobin a1c"], "glucose": ["glucose", "blood sugar"], "creatinine": ["creatinine"], "egfr": ["egfr", "kidney function"],
    "bun": ["bun"], "potassium": ["potassium"], "sodium": ["sodium"], "chloride": ["chloride"], "calcium": ["calcium"], "co2": ["bicarbonate"],
    "cholesterol": ["cholesterol", "total cholesterol"], "ldl": ["ldl"], "hdl": ["hdl"], "triglycerides": ["triglycerides"], "hemoglobin": ["hemoglobin", "hgb"],
    "hematocrit": ["hematocrit"], "wbc": ["white count", "wbc"], "platelets": ["platelets"], "alt": ["alt"], "ast": ["ast"], "albumin": ["albumin"],
    "bilirubin": ["bilirubin"], "uacr": ["urine microalbumin"], "psa": ["psa"], "tsh": ["tsh"], "inr": ["inr"], "troponin": ["troponin"],
    "ntprobnp": ["bnp"], "ferritin": ["ferritin"], "weight": ["weight"], "height": ["height"], "bmi": ["bmi"], "bp": ["blood pressure", "bp"],
    "heart_rate": ["heart rate", "pulse"], "resp_rate": ["respiratory rate"], "temperature": ["temperature"], "oxygen": ["oxygen saturation"],
    "pain": ["pain score"], "smoking": ["smoking status"],
}
COND_SURFACE = {
    "diabetes": ["diabetes", "type 2 diabetes"], "prediabetes": ["prediabetes"], "hypertension": ["hypertension", "high blood pressure"],
    "ckd": ["chronic kidney disease", "ckd"], "asthma": ["asthma"], "copd": ["copd"], "heart_failure": ["heart failure"],
    "cad": ["coronary artery disease", "heart disease"], "lipids": ["high cholesterol", "hyperlipidemia"], "obesity": ["obesity"], "anemia": ["anemia"],
    "depression": ["depression"], "anxiety": ["anxiety"], "arthritis": ["osteoarthritis", "arthritis"], "cancer": ["cancer"], "sleep_apnea": ["sleep apnea"],
    "afib": ["atrial fibrillation", "afib"], "dementia": ["dementia", "alzheimer's"], "covid": ["covid"], "migraine": ["migraines"],
    "uti": ["a uti", "urinary tract infections"], "sinusitis": ["sinusitis"], "back_pain": ["back pain"], "epilepsy": ["epilepsy", "seizures"],
    "pain": ["chronic pain"], "gout": ["gout"], "osteoporosis": ["osteoporosis"], "hypothyroidism": ["hypothyroidism"],
    "allergic_rhinitis": ["allergic rhinitis", "hay fever"], "sepsis": ["sepsis"],
}
MEDCLASS_SURFACE = {
    "bp_meds": ["blood pressure medication"], "statin": ["a statin", "statins"], "insulin": ["insulin"], "inhaler": ["an inhaler"],
    "opioid": ["opioids", "an opioid"], "antibiotic": ["antibiotics", "an antibiotic"], "blood_thinner": ["a blood thinner", "blood thinners"],
    "diabetes_meds": ["diabetes medication"], "contraceptive": ["birth control"], "antihistamine": ["an antihistamine"], "nsaid": ["an nsaid"],
    "beta_blocker": ["a beta blocker"], "ace_inhibitor": ["an ace inhibitor"], "diuretic": ["a diuretic"],
}
VAX_SURFACE = {"flu": ["flu"], "covid_vax": ["covid"], "shingles": ["shingles"], "tetanus": ["tetanus"], "pneumococcal": ["pneumonia"]}
ALLERGEN_SURFACE = {"penicillin v": "penicillin", "peanut": "peanuts", "cows milk": "milk", "eggs": "eggs", "shellfish": "shellfish", "tree nut": "tree nuts",
                    "latex": "latex", "bee venom": "bee stings", "sulfamethoxazole trimethoprim": "sulfa", "aspirin": "aspirin", "fish": "fish",
                    "wheat": "wheat", "animal dander": "pet dander", "house dust mite": "dust mites", "grass pollen": "grass pollen", "tree pollen": "tree pollen",
                    "mold": "mold", "lisinopril": "lisinopril", "cefdinir": "cefdinir", "soya bean": "soy"}
ABSENT_LABS = ["a1c", "psa", "tsh", "inr", "ldl", "troponin", "ferritin", "ntprobnp", "uacr", "alt"]
NEVER_CONDS = ["diabetes", "hypertension", "asthma", "copd", "heart_failure", "ckd", "cancer", "afib", "depression", "dementia", "epilepsy"]
NEVER_MEDS = ["med:metformin", "med:lisinopril", "medclass:statin", "medclass:insulin", "medclass:blood_thinner", "medclass:opioid", "med:albuterol",
              "med:hydrochlorothiazide", "med:amlodipine", "medclass:beta_blocker"]

CATEGORIES = [
    ("latest", "Latest result"), ("in_year", "Result in a given year"), ("trend", "Trend"),
    ("cond_active", "Condition, active"), ("cond_resolved", "Condition, resolved"), ("cond_never", "Condition, never recorded"),
    ("problems", "Problem list"), ("med_active", "Medication, current"), ("med_past", "Medication, stopped"), ("med_never", "Medication, never prescribed"),
    ("meds", "Medication list"), ("med_start", "Medication start date"), ("allergies", "Allergy list"), ("allergy_yes", "Allergy, present"),
    ("allergy_no", "Allergy, absent"), ("vaccine", "Last vaccine"), ("er", "ER visits, past year"), ("last_visit", "Last visit"), ("age", "Age"),
    ("absent", "Lab never done"), ("unsupported", "Outside the record"), ("advice", "Treatment advice"),
]
TRAPS = {"cond_resolved", "med_past", "cond_never", "med_never", "allergy_no", "absent", "unsupported", "advice"}


def pronouns(sex: str) -> dict:
    if sex == "male":
        return {"subj": "he", "obj": "him", "poss": "his", "is": "is", "has": "has", "does": "does", "was": "was"}
    if sex == "female":
        return {"subj": "she", "obj": "her", "poss": "her", "is": "is", "has": "has", "does": "does", "was": "was"}
    return {"subj": "they", "obj": "them", "poss": "their", "is": "are", "has": "have", "does": "do", "was": "were"}


def fill(template: str, slots: dict) -> str:
    out = template
    for k, v in slots.items():
        out = out.replace("{" + k + "}", str(v))
    return re.sub(r"\s+", " ", out).strip()


def build(charts: list[dict], lexicon: dict, heldout: dict, seed: int = 7) -> list[dict]:
    concepts = {c["key"]: c for c in lexicon["concepts"]}
    from .lexicon import CONDITION_GROUPS
    groups = {g[0] for g in CONDITION_GROUPS}
    group_of: dict[str, str] = {}
    single_of: dict[str, str] = {}
    for c in lexicon["concepts"]:
        if c["key"].startswith("cond:"):
            for code in c["codes"]:
                if c["key"][5:] in groups:
                    group_of.setdefault(code, c["key"][5:])
                else:
                    single_of[code] = c["key"]
    qs: list[dict] = []

    for chart in charts:
        rng = random.Random(f"{seed}:{chart['id']}")
        p = pronouns(chart["sex"])
        items: list[tuple[str, str, dict, dict]] = []  # (category, intent, slots, gold)
        recs = [r for r in chart["records"] if not r.get("noresult")]
        obs_codes = {r["code"] for r in recs if r["type"] == "Observation"}

        def obs_present(min_n=1):
            out = []
            for key, surf in OBS_SURFACE.items():
                c = concepts[f"obs:{key}"]
                n = sum(1 for r in recs if r["type"] == "Observation" and r["code"] in c["codes"])
                if n >= min_n:
                    out.append(key)
            return out

        present = obs_present()
        if present:
            for key in rng.sample(present, min(2, len(present))):
                c = concepts[f"obs:{key}"]
                items.append(("latest", "latest_value", {"concept": rng.choice(OBS_SURFACE[key])},
                              {"intent": "latest_value", "id": gold.latest(chart, c["codes"])}))
            many = [k for k in obs_present(3) if k != "smoking"]
            if many:
                key = rng.choice(many)
                c = concepts[f"obs:{key}"]
                ids, direction = gold.trend(chart, c["codes"])
                items.append(("trend", "trend", {"concept": rng.choice(OBS_SURFACE[key])}, {"intent": "trend", "ids": ids, "direction": direction}))
                years = sorted({r["date"][:4] for r in recs if r["type"] == "Observation" and r["code"] in c["codes"]})
                if len(years) > 1:
                    yr = rng.choice(years[:-1])
                    items.append(("in_year", "latest_in_year", {"concept": rng.choice(OBS_SURFACE[key]), "year": yr},
                                  {"intent": "latest_value", "id": gold.latest(chart, c["codes"], f"{yr}-01-01", f"{yr}-12-31")}))
        absent = [k for k in ABSENT_LABS if not (set(concepts[f"obs:{k}"]["codes"]) & obs_codes)]
        if absent:
            key = rng.choice(absent)
            items.append(("absent", "latest_value", {"concept": OBS_SURFACE[key][0]}, {"expect": "abstain"}))

        # conditions, by the name a clinician would use
        conds = [r for r in recs if r["type"] == "Condition"]
        by_concept: dict[str, list[dict]] = defaultdict(list)
        for r in conds:
            g = group_of.get(r["code"])
            if g and g in COND_SURFACE:
                by_concept[f"cond:{g}"].append(r)
            elif re.fullmatch(r"[A-Za-z' -]+", r["name"]) and len(r["name"].split()) <= 4:
                by_concept[single_of[r["code"]]].append(r)

        def cond_surface(key):
            k = key[5:]
            return rng.choice(COND_SURFACE[k]) if k in COND_SURFACE else concepts[key]["label"].lower()

        active = sorted(k for k, rs in by_concept.items() if gold.condition_state(chart, concepts[k]["codes"])[0] in ("active", "recorded"))
        resolved = sorted(k for k, rs in by_concept.items() if gold.condition_state(chart, concepts[k]["codes"])[0] == "resolved")
        if active:
            k = rng.choice(active)
            st, codes = gold.condition_state(chart, concepts[k]["codes"])
            items.append(("cond_active", "has_condition", {"concept": cond_surface(k)}, {"intent": "has_condition", "state": st, "codes": codes}))
        if resolved:
            k = rng.choice(resolved)
            st, codes = gold.condition_state(chart, concepts[k]["codes"])
            items.append(("cond_resolved", "has_condition", {"concept": cond_surface(k)}, {"intent": "has_condition", "state": st, "codes": codes}))
        never = [k for k in NEVER_CONDS if concepts[f"cond:{k}"]["codes"] and gold.condition_state(chart, concepts[f"cond:{k}"]["codes"])[0] == "never"]
        if never:
            k = rng.choice(never)
            items.append(("cond_never", "has_condition", {"concept": rng.choice(COND_SURFACE[k])}, {"intent": "has_condition", "state": "never", "codes": []}))
        items.append(("problems", "problem_list", {}, {"intent": "problem_list", "codes": gold.active_problems(chart)}))

        # medications
        meds = [r for r in recs if r["type"] == "MedicationRequest"]
        med_keys = []
        for c in concepts.values():
            if c["key"].startswith("med:") and len(c["label"].split()) <= 2 and not c["label"].lower().startswith("insulin"):
                if any(r["code"] in c["codes"] for r in meds):
                    med_keys.append(c["key"])
        class_keys = [f"medclass:{k}" for k in MEDCLASS_SURFACE if any(r["code"] in concepts[f"medclass:{k}"]["codes"] for r in meds)]

        def med_surface(key):
            return rng.choice(MEDCLASS_SURFACE[key[9:]]) if key.startswith("medclass:") else concepts[key]["label"].lower()

        act = sorted(k for k in med_keys + class_keys if gold.med_state(chart, concepts[k]["codes"])[0] in ("active", "last_stay"))
        past = sorted(k for k in med_keys if gold.med_state(chart, concepts[k]["codes"])[0] == "past")
        if act:
            k = rng.choice(act)
            st, codes = gold.med_state(chart, concepts[k]["codes"])
            items.append(("med_active", "on_med", {"concept": med_surface(k)}, {"intent": "on_med", "state": st, "codes": codes}))
            ing = [x for x in act if x.startswith("med:")]
            if ing:
                k = rng.choice(ing)
                items.append(("med_start", "med_start", {"concept": med_surface(k)}, {"intent": "med_start", "date": gold.med_start(chart, concepts[k]["codes"])}))
        if past:
            k = rng.choice(past)
            items.append(("med_past", "on_med", {"concept": med_surface(k)}, {"intent": "on_med", "state": "past", "codes": []}))
        nev = [k for k in NEVER_MEDS if k in concepts and concepts[k]["codes"] and gold.med_state(chart, concepts[k]["codes"])[0] == "never"]
        if nev:
            k = rng.choice(nev)
            items.append(("med_never", "on_med", {"concept": med_surface(k)}, {"intent": "on_med", "state": "never", "codes": []}))
        items.append(("meds", "med_list", {}, {"intent": "med_list", "codes": gold.active_meds(chart)}))

        # allergies and vaccines: hospital records in this dataset carry neither, so they are not asked about
        if chart.get("source") != "hospital":
            items.append(("allergies", "allergy_list", {}, {"intent": "allergy_list", "codes": gold.allergies(chart)}))
            mine = set(gold.allergies(chart))
            allergen = [(c, ALLERGEN_SURFACE[_allergen_name(c)]) for c in concepts.values()
                        if c["kind"] == "allergy" and _allergen_name(c) in ALLERGEN_SURFACE]
            yes = [x for x in allergen if set(x[0]["codes"]) & mine]
            no = [x for x in allergen if not set(x[0]["codes"]) & mine and _allergen_name(x[0]) in ("penicillin v", "peanut", "latex", "shellfish", "sulfamethoxazole trimethoprim", "aspirin")]
            if yes:
                c, s = rng.choice(yes)
                items.append(("allergy_yes", "allergy_check", {"concept": s}, {"intent": "allergy_check", "allergic": True}))
            if no:
                c, s = rng.choice(no)
                items.append(("allergy_no", "allergy_check", {"concept": s}, {"intent": "allergy_check", "allergic": False}))

            # vaccines, visits, age
            vk = rng.choice(sorted(VAX_SURFACE))
            items.append(("vaccine", "vaccine_last", {"concept": VAX_SURFACE[vk][0]}, {"intent": "vaccine_last", "date": gold.last_vaccine(chart, concepts[f"vax:{vk}"]["codes"])}))
            if vk != "flu":
                items.append(("vaccine", "vaccine_last", {"concept": "flu"}, {"intent": "vaccine_last", "date": gold.last_vaccine(chart, concepts["vax:flu"]["codes"])}))
        items.append(("er", "er_visits", {}, {"intent": "er_visits", "count": gold.er_count(chart, minus_months(chart["asOf"], 12), chart["asOf"])}))
        items.append(("last_visit", "last_visit", {}, {"intent": "last_visit", "id": gold.last_visit(chart)}))
        items.append(("age", "age", {}, {"intent": "age", "years": gold.age(chart)}))
        items.append(("unsupported", "unsupported", {}, {"expect": "abstain"}))
        items.append(("advice", "advice", {}, {"expect": "decline"}))

        for n, (cat, intent, slots, g) in enumerate(items):
            for split, bank in (("dev", None), ("heldout", heldout)):
                if intent == "unsupported":
                    tmpl = rng.choice(DEV_UNSUPPORTED if split == "dev" else heldout["unsupported"])
                elif intent == "advice":
                    tmpl = rng.choice(DEV_ADVICE if split == "dev" else heldout["advice"])
                else:
                    tmpl = rng.choice(DEV[intent] if split == "dev" else heldout["templates"][intent])
                qs.append({"id": f"{chart['id'][:8]}-{n:02d}-{split}", "patient": chart["id"], "category": cat, "split": split,
                           "question": fill(tmpl, {**p, **slots}), "gold": g})
    return qs


def _allergen_name(c: dict) -> str:
    from .lexicon import norm
    return norm(c["label"])


# ---- grading ---------------------------------------------------------------------------------

def grade(ans: dict, g: dict) -> bool:
    status = ans.get("status")
    if g.get("expect") == "abstain":
        return status in ("not_found", "unsupported")
    if g.get("expect") == "decline":
        return status == "advice"
    if status != "answered" or ans.get("intent") != g["intent"]:
        return False
    r = ans.get("result", {})
    it = g["intent"]
    if it == "latest_value":
        return r.get("id") == g["id"]
    if it == "trend":
        return r.get("ids") == g["ids"] and r.get("direction") == g["direction"]
    if it in ("has_condition", "on_med"):
        return r.get("state") == g["state"] and (g["state"] not in ("active", "recorded", "last_stay") or r.get("codes") == g["codes"])
    if it in ("problem_list", "med_list", "allergy_list"):
        return r.get("codes") == g["codes"]
    if it == "med_start":
        return r.get("date") == g["date"]
    if it == "allergy_check":
        return r.get("allergic") == g["allergic"]
    if it == "vaccine_last":
        return r.get("date") == g["date"]
    if it == "er_visits":
        return r.get("count") == g["count"]
    if it == "last_visit":
        return r.get("id") == g["id"]
    if it == "age":
        return r.get("years") == g["years"]
    return False


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d, (c + m) / d


def evaluate(answerer, charts: list[dict], questions: list[dict], keep: int = 0) -> dict:
    by_patient = defaultdict(list)
    for q in questions:
        by_patient[q["patient"]].append(q)
    rows = []
    for chart in charts:
        for q in by_patient.get(chart["id"], []):
            ans = answerer.ask(chart, q["question"])
            ok = grade(ans, q["gold"])
            v = check(chart, ans, q["question"])
            rows.append({"id": q["id"], "category": q["category"], "split": q["split"], "correct": ok, "verified": v["ok"],
                         "status": ans.get("status"), "intent": ans.get("intent"), "question": q["question"],
                         "answer": ans.get("text", "")[:300], "problems": v["problems"][:3]})
    return summarize(rows)


def summarize(rows: list[dict]) -> dict:
    out = {"total": {}, "by_split": {}, "by_category": {}, "failures": []}

    def stats(rs):
        k, n = sum(r["correct"] for r in rs), len(rs)
        lo, hi = wilson(k, n)
        unverified = sum(1 for r in rs if not r["verified"])
        false_answer = sum(1 for r in rs if not r["correct"] and r["status"] == "answered")
        return {"n": n, "correct": k, "accuracy": round(k / n, 4) if n else 0, "ci": [round(lo, 4), round(hi, 4)],
                "unverified": unverified, "wrong_answers": false_answer}

    out["total"] = stats(rows)
    for split in ("dev", "heldout"):
        rs = [r for r in rows if r["split"] == split]
        out["by_split"][split] = stats(rs)
    for cat, _ in CATEGORIES:
        out["by_category"][cat] = {s: stats([r for r in rows if r["category"] == cat and r["split"] == s]) for s in ("dev", "heldout")}
    fails = [r for r in rows if not r["correct"]]
    out["failures"] = fails[:400]
    return out


def save_questions(qs: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")


def load_questions(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]
