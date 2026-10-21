"""The vocabulary: which words in a question mean which codes in the record.

Labs and vitals are mapped by hand to LOINC codes. Conditions, medications, vaccines and
allergens are read from the records themselves (every SNOMED, RxNorm and CVX code seen), then
grouped the way clinicians talk: "high blood pressure", "a statin", "blood thinner", "flu shot".

The result is plain JSON so the browser uses exactly the same vocabulary as Python.
"""

from __future__ import annotations

import re
from collections import defaultdict

# ---- labs and vitals --------------------------------------------------------------------

OBS = [
    # key, label, LOINC codes (preferred first), phrases
    ("a1c", "Hemoglobin A1c", ["4548-4"], ["a1c", "hba1c", "hemoglobin a1c", "haemoglobin a1c", "glycated hemoglobin", "glycohemoglobin"]),
    ("glucose", "Glucose", ["2339-0", "2345-7"], ["glucose", "blood glucose", "blood sugar", "sugar", "glucose level"]),
    ("creatinine", "Creatinine", ["38483-4", "2160-0"], ["creatinine", "creat", "serum creatinine"]),
    ("egfr", "eGFR", ["33914-3"], ["egfr", "gfr", "kidney function", "renal function", "glomerular filtration rate", "filtration rate"]),
    ("bun", "Urea nitrogen (BUN)", ["6299-2", "3094-0"], ["bun", "urea nitrogen", "blood urea nitrogen", "urea"]),
    ("potassium", "Potassium", ["6298-4", "2823-3"], ["potassium", "k level"]),
    ("sodium", "Sodium", ["2947-0", "2951-2"], ["sodium", "na level"]),
    ("chloride", "Chloride", ["2069-3", "2075-0"], ["chloride"]),
    ("calcium", "Calcium", ["49765-1", "17861-6"], ["calcium"]),
    ("co2", "Carbon dioxide", ["20565-8", "2028-9"], ["co2", "bicarbonate", "bicarb", "carbon dioxide"]),
    ("cholesterol", "Total cholesterol", ["2093-3"], ["cholesterol", "total cholesterol", "cholesterol level"]),
    ("ldl", "LDL cholesterol", ["18262-6"], ["ldl", "ldl cholesterol", "bad cholesterol"]),
    ("hdl", "HDL cholesterol", ["2085-9"], ["hdl", "hdl cholesterol", "good cholesterol"]),
    ("triglycerides", "Triglycerides", ["2571-8"], ["triglycerides", "triglyceride", "trigs", "tg"]),
    ("hemoglobin", "Hemoglobin", ["718-7"], ["hemoglobin", "haemoglobin", "hgb", "hb"]),
    ("hematocrit", "Hematocrit", ["4544-3", "20570-8"], ["hematocrit", "hct"]),
    ("wbc", "White blood cells", ["6690-2"], ["wbc", "white count", "white blood cells", "white blood cell count", "leukocytes"]),
    ("platelets", "Platelets", ["777-3"], ["platelets", "platelet count", "plt"]),
    ("alt", "ALT", ["1742-6"], ["alt", "alanine aminotransferase", "sgpt"]),
    ("ast", "AST", ["1920-8"], ["ast", "aspartate aminotransferase", "sgot"]),
    ("albumin", "Albumin", ["1751-7"], ["albumin"]),
    ("bilirubin", "Bilirubin", ["1975-2"], ["bilirubin", "total bilirubin", "bili"]),
    ("uacr", "Urine albumin/creatinine ratio", ["14959-1"], ["microalbumin", "urine microalbumin", "albumin creatinine ratio", "uacr", "acr"]),
    ("psa", "PSA", ["2857-1"], ["psa", "prostate specific antigen"]),
    ("tsh", "TSH", ["3016-3"], ["tsh", "thyroid stimulating hormone", "thyroid function"]),
    ("inr", "INR", ["6301-6"], ["inr"]),
    ("troponin", "Troponin I", ["89579-7"], ["troponin"]),
    ("ntprobnp", "NT-proBNP", ["33762-6"], ["bnp", "nt probnp", "probnp"]),
    ("ferritin", "Ferritin", ["2276-4"], ["ferritin"]),
    ("weight", "Weight", ["29463-7"], ["weight", "body weight", "wt"]),
    ("height", "Height", ["8302-2"], ["height", "body height", "ht"]),
    ("bmi", "BMI", ["39156-5"], ["bmi", "body mass index"]),
    ("bp", "Blood pressure", ["85354-9"], ["blood pressure", "bp", "blood pressures"]),
    ("heart_rate", "Heart rate", ["8867-4"], ["heart rate", "pulse", "hr", "pulse rate"]),
    ("resp_rate", "Respiratory rate", ["9279-1"], ["respiratory rate", "breathing rate", "rr", "resp rate"]),
    ("temperature", "Temperature", ["8310-5"], ["temperature", "temp", "body temperature"]),
    ("oxygen", "Oxygen saturation", ["2708-6", "59408-5"], ["oxygen saturation", "o2 sat", "o2 saturation", "spo2", "sats", "oxygen level", "pulse ox"]),
    ("pain", "Pain score", ["72514-3"], ["pain score", "pain level", "pain severity"]),
    ("smoking", "Smoking status", ["72166-2"], ["smoking status", "smoking", "smoker", "smoke", "tobacco", "tobacco use", "cigarettes"]),
]

# ---- conditions: groups over the SNOMED names found in the records ---------------------

CONDITION_GROUPS = [
    ("diabetes", "Diabetes", r"^(diabetes mellitus type [12]|type [12] diabetes mellitus)$",
     ["diabetes", "diabetic", "dm", "t2dm", "dm2", "type 2 diabetes", "diabetes mellitus", "sugar diabetes"]),
    ("prediabetes", "Prediabetes", r"^prediabetes$", ["prediabetes", "pre diabetes", "prediabetic", "borderline diabetes"]),
    ("hypertension", "Hypertension", r"hypertension$", ["hypertension", "htn", "high blood pressure", "elevated blood pressure", "hypertensive"]),
    ("ckd", "Chronic kidney disease", r"^chronic kidney disease", ["ckd", "chronic kidney disease", "kidney disease", "renal disease", "chronic renal disease", "kidney failure"]),
    ("asthma", "Asthma", r"asthma", ["asthma", "asthmatic"]),
    ("copd", "COPD", r"emphysema|chronic obstructive", ["copd", "emphysema", "chronic obstructive pulmonary disease", "chronic bronchitis"]),
    ("heart_failure", "Heart failure", r"heart failure", ["heart failure", "chf", "congestive heart failure", "hf"]),
    ("cad", "Coronary heart disease", r"ischemic heart disease|coronary|myocardial infarction", ["cad", "coronary artery disease", "heart disease", "ischemic heart disease", "coronary disease", "heart attack", "mi"]),
    ("lipids", "High cholesterol", r"hyperlipidemia|hypertriglyceridemia|dyslipidemia|hypercholesterolemia", ["high cholesterol", "hyperlipidemia", "hld", "dyslipidemia", "hypercholesterolemia", "high triglycerides"]),
    ("obesity", "Obesity", r"obesity", ["obesity", "obese"]),
    ("anemia", "Anemia", r"anemia", ["anemia", "anaemia", "anemic"]),
    ("depression", "Depression", r"depress", ["depression", "depressed", "mdd", "major depression"]),
    ("anxiety", "Anxiety", r"anxiety", ["anxiety", "anxious", "panic"]),
    ("arthritis", "Osteoarthritis", r"osteoarthritis|arthritis", ["osteoarthritis", "arthritis", "oa", "degenerative joint disease"]),
    ("cancer", "Cancer", r"neoplasm|carcinoma|cancer|leukemia|lymphoma", ["cancer", "malignancy", "tumor", "tumour", "carcinoma"]),
    ("sleep_apnea", "Sleep apnea", r"sleep apnea", ["sleep apnea", "osa", "obstructive sleep apnea", "apnea"]),
    ("afib", "Atrial fibrillation", r"atrial fibrillation", ["atrial fibrillation", "afib", "a fib", "af"]),
    ("stroke", "Stroke", r"stroke|cerebrovascular", ["stroke", "cva", "cerebrovascular accident"]),
    ("dementia", "Dementia", r"alzheimer|dementia", ["dementia", "alzheimers", "alzheimer", "alzheimers disease", "memory loss"]),
    ("covid", "COVID", r"coronavirus 2", ["covid", "covid 19", "coronavirus", "sars cov 2"]),
    ("migraine", "Migraine", r"migraine", ["migraine", "migraines"]),
    ("uti", "Urinary tract infection", r"urinary tract infection|cystitis", ["uti", "utis", "urinary tract infection", "bladder infection"]),
    ("sinusitis", "Sinusitis", r"sinusitis", ["sinusitis", "sinus infection"]),
    ("back_pain", "Back pain", r"back pain", ["back pain", "low back pain", "lbp"]),
    ("fracture", "Fracture", r"fracture", ["fracture", "broken bone", "fractures"]),
    ("epilepsy", "Epilepsy", r"epilepsy|seizure disorder", ["epilepsy", "seizures", "seizure disorder", "seizure"]),
    ("osteoporosis", "Osteoporosis", r"osteoporosis", ["osteoporosis"]),
    ("hypothyroidism", "Hypothyroidism", r"hypothyroid", ["hypothyroidism", "underactive thyroid", "low thyroid"]),
    ("gout", "Gout", r"gout", ["gout"]),
    ("pain", "Chronic pain", r"chronic pain", ["chronic pain"]),
    ("sepsis", "Sepsis", r"sepsis", ["sepsis"]),
    ("allergic_rhinitis", "Allergic rhinitis", r"allergic rhinitis", ["allergic rhinitis", "hay fever", "seasonal allergies"]),
]

# ---- medications: ingredient classes ----------------------------------------------------

MED_CLASSES = [
    ("bp_meds", "Blood pressure medication",
     ["lisinopril", "hydrochlorothiazide", "amlodipine", "losartan", "metoprolol", "carvedilol", "atenolol", "valsartan", "chlorthalidone", "enalapril", "furosemide"],
     ["blood pressure medication", "blood pressure medications", "blood pressure meds", "blood pressure med", "bp meds", "bp med", "bp medication",
      "antihypertensive", "antihypertensives", "blood pressure pills", "blood pressure pill"]),
    ("statin", "Statin", ["simvastatin", "atorvastatin", "rosuvastatin", "pravastatin", "lovastatin"],
     ["statin", "statins", "cholesterol medication", "cholesterol meds", "cholesterol med", "cholesterol pill"]),
    ("insulin", "Insulin", ["insulin"], ["insulin"]),
    ("inhaler", "Inhaler", ["albuterol", "fluticasone", "budesonide", "salmeterol", "ipratropium", "tiotropium", "formoterol"],
     ["inhaler", "inhalers", "puffer", "nebulizer"]),
    ("rescue_inhaler", "Rescue inhaler", ["albuterol"], ["rescue inhaler", "albuterol inhaler"]),
    ("opioid", "Opioid", ["oxycodone", "hydrocodone", "tramadol", "morphine", "fentanyl", "codeine", "hydromorphone", "meperidine"],
     ["opioid", "opioids", "narcotic", "narcotics", "opiates", "opiate", "pain pills"]),
    ("antibiotic", "Antibiotic", ["amoxicillin", "penicillin v", "cefuroxime", "cephalexin", "ciprofloxacin", "doxycycline", "nitrofurantoin",
                                  "sulfamethoxazole", "trimethoprim", "azithromycin", "clindamycin", "clavulanate"],
     ["antibiotic", "antibiotics", "abx"]),
    ("blood_thinner", "Blood thinner", ["clopidogrel", "warfarin", "apixaban", "rivaroxaban", "heparin", "aspirin", "dabigatran"],
     ["blood thinner", "blood thinners", "anticoagulant", "anticoagulants", "antiplatelet", "anticoagulation"]),
    ("diabetes_meds", "Diabetes medication", ["metformin", "insulin", "glipizide", "sitagliptin", "liraglutide", "empagliflozin", "glyburide"],
     ["diabetes medication", "diabetes medications", "diabetes meds", "diabetic medication", "diabetes med"]),
    ("contraceptive", "Hormonal contraceptive", ["norethindrone", "ethinyl estradiol", "levonorgestrel", "drospirenone", "norgestimate", "etonogestrel",
                                                  "medroxyprogesterone", "dienogest", "norelgestromin"],
     ["birth control", "contraceptive", "contraception", "the pill", "oral contraceptive", "contraceptives"]),
    ("antihistamine", "Antihistamine", ["loratadine", "cetirizine", "fexofenadine", "diphenhydramine", "astemizole"],
     ["antihistamine", "antihistamines", "allergy medication", "allergy meds"]),
    ("nsaid", "NSAID", ["ibuprofen", "naproxen"], ["nsaid", "nsaids", "anti inflammatory", "anti inflammatories"]),
    ("beta_blocker", "Beta blocker", ["metoprolol", "carvedilol", "atenolol", "propranolol"], ["beta blocker", "beta blockers"]),
    ("ace_inhibitor", "ACE inhibitor", ["lisinopril", "enalapril", "ramipril", "benazepril"], ["ace inhibitor", "ace inhibitors", "acei"]),
    ("diuretic", "Diuretic", ["hydrochlorothiazide", "furosemide", "chlorthalidone", "spironolactone"], ["diuretic", "diuretics", "water pill", "water pills"]),
    ("steroid_inhaled", "Inhaled steroid", ["fluticasone", "budesonide"], ["inhaled steroid", "steroid inhaler", "ics"]),
]
# common short names for ingredients
MED_ALIASES = {"hydrochlorothiazide": ["hctz"], "acetaminophen": ["tylenol", "paracetamol", "apap"], "ibuprofen": ["advil", "motrin"],
               "naproxen": ["aleve"], "amoxicillin": ["amox"], "sulfamethoxazole": ["bactrim", "septra", "smx"], "clopidogrel": ["plavix"],
               "metoprolol": ["toprol"], "amlodipine": ["norvasc"], "simvastatin": ["zocor"], "lisinopril": ["zestril", "prinivil"],
               "metformin": ["glucophage"], "nitroglycerin": ["nitro"], "albuterol": ["ventolin", "proair", "salbutamol"],
               "insulin": [], "tacrolimus": ["prograf"], "fluticasone": ["flovent"], "oxycodone": ["oxycontin"], "hydrocodone": ["vicodin", "norco"],
               "aspirin": ["asa"], "warfarin": ["coumadin"], "furosemide": ["lasix"]}

SALTS = {"hydrochloride", "sodium", "potassium", "succinate", "hyclate", "bitartrate", "propionate", "hydrobromide", "maleate", "sulfate",
         "calcium", "besylate", "tartrate", "citrate", "macrocrystals", "monohydrate", "valerate", "acetate", "fumarate", "mesylate"}

# ---- vaccines ------------------------------------------------------------------------------

VACCINE_GROUPS = [
    ("flu", "Influenza vaccine", r"influenza", ["flu", "flu shot", "flu vaccine", "influenza", "influenza vaccine", "flu jab"]),
    ("tetanus", "Tetanus vaccine", r"^(td|tdap|dtap)\b|tetanus", ["tetanus", "tdap", "td", "tetanus shot", "dtap", "tetanus booster"]),
    ("covid_vax", "COVID vaccine", r"covid", ["covid", "covid vaccine", "covid 19", "covid shot", "covid booster", "coronavirus vaccine", "covid 19 vaccine"]),
    ("shingles", "Shingles vaccine", r"zoster", ["shingles", "zoster", "shingrix", "shingles vaccine"]),
    ("pneumococcal", "Pneumococcal vaccine", r"pneumococcal", ["pneumonia", "pneumococcal", "pneumovax", "prevnar", "pneumonia vaccine"]),
    ("hpv", "HPV vaccine", r"hpv", ["hpv", "gardasil", "hpv vaccine"]),
    ("hepb", "Hepatitis B vaccine", r"hep b", ["hepatitis b", "hep b"]),
    ("hepa", "Hepatitis A vaccine", r"hep a", ["hepatitis a", "hep a"]),
    ("mmr", "MMR vaccine", r"mmr", ["mmr", "measles", "mumps", "rubella"]),
    ("polio", "Polio vaccine", r"\bipv\b", ["polio", "ipv"]),
    ("varicella", "Chickenpox vaccine", r"varicella", ["chickenpox", "chicken pox", "varicella"]),
    ("meningococcal", "Meningococcal vaccine", r"meningococcal", ["meningitis", "meningococcal"]),
    ("rotavirus", "Rotavirus vaccine", r"rotavirus", ["rotavirus"]),
    ("hib", "Hib vaccine", r"\bhib\b", ["hib"]),
]

# ---- allergens: extra ways people name them -------------------------------------------

ALLERGEN_ALIASES = {
    "peanut": ["peanuts", "peanut"], "tree nut": ["tree nuts", "nuts"], "shellfish": ["shellfish", "shrimp", "seafood"],
    "fish": ["fish"], "cows milk": ["milk", "dairy", "lactose"], "eggs": ["eggs", "egg"], "wheat": ["wheat", "gluten"],
    "soya bean": ["soy", "soya"], "latex": ["latex"], "bee venom": ["bees", "bee stings", "bee sting", "bee venom"],
    "penicillin v": ["penicillin", "pcn", "penicillins"], "aspirin": ["aspirin", "asa"],
    "sulfamethoxazole trimethoprim": ["sulfa", "sulfa drugs", "bactrim", "sulfonamides"],
    "animal dander": ["animal dander", "dander", "pet dander", "cats", "dogs", "pets"], "house dust mite": ["dust mites", "dust mite", "dust"],
    "grass pollen": ["grass pollen", "grass", "pollen"], "tree pollen": ["tree pollen", "trees"], "mold": ["mold", "mould"],
    "allergic disposition": [], "allergy to substance": [],
}


# dose-form and packaging words that follow a '/' in RxNorm names ('1 MG/ML Auto-Injector')
FORMS = {"oral", "tablet", "tablets", "capsule", "solution", "suspension", "injectable", "injection", "inhalation", "inhaler", "metered",
         "dose", "dry", "powder", "breath", "actuated", "auto", "injector", "prefilled", "syringe", "topical", "cream", "mucosal", "spray",
         "transdermal", "system", "pack", "day", "mg", "ml", "per", "extended", "release", "chewable", "vaginal", "intrauterine", "unt",
         "actuat", "hr", "film", "coated", "delayed", "patch", "gel", "ointment", "drops", "ophthalmic", "nasal", "kit", "cartridge", "pen"}


def norm(text: str) -> str:
    """Lowercase, drop apostrophes, turn every other non-alphanumeric run into one space."""
    text = text.lower().replace("’", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def ingredients(display: str) -> list[str]:
    """RxNorm display -> ingredient names. '24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet' -> ['metformin']."""
    text = re.sub(r"\[[^\]]*\]", "", display)  # brand in brackets
    text = re.sub(r"[{}()]", " ", text)
    out = []
    for part in text.split("/"):
        words = part.split()
        # skip leading pack counts, durations and NDA numbers: '28', '24 HR', '120 ACTUAT', 'NDA020983', 'Abuse-Deterrent'
        i = 0
        while i < len(words) and (re.fullmatch(r"\d+(\.\d+)?|NDA\d+|HR|ACTUAT|DAY|ML|Abuse-Deterrent|Pack", words[i])):
            i += 1
        name = []
        for w in words[i:]:
            if re.match(r"\d", w):
                break
            name.append(w)
        full = [t for t in norm(" ".join(name)).split() if t not in FORMS]
        n = " ".join(t for t in full if t not in SALTS)
        if n in ("chloride", "ferrous"):  # 'sodium chloride', 'ferrous sulfate': the salt is the drug
            n = " ".join(full)
        if n and n not in ("inert ingredients", "inert"):
            out.append(n)
    return out


def brands(display: str) -> list[str]:
    return [norm(b) for b in re.findall(r"\[([^\]]+)\]", display)]


def build(charts: list[dict]) -> dict:
    """Build the vocabulary from every chart in the cohort."""
    cond_names: dict[str, str] = {}
    med_names: dict[str, str] = {}
    vax_names: dict[str, str] = {}
    allergy_names: dict[str, str] = {}
    obs_codes: set[str] = set()
    for chart in charts:
        for r in chart["records"]:
            t = r["type"]
            if t == "Condition":
                cond_names[r["code"]] = r["name"]
            elif t == "MedicationRequest":
                med_names[r["code"]] = r["name"]
            elif t == "Immunization":
                vax_names[r["code"]] = r["name"]
            elif t == "AllergyIntolerance":
                allergy_names[r["code"]] = r["name"]
            elif t == "Observation":
                obs_codes.add(r["code"])

    concepts = []

    for key, label, codes, phrases in OBS:
        concepts.append({"key": f"obs:{key}", "kind": "obs", "label": label, "codes": codes, "phrases": phrases})

    grouped: set[str] = set()
    for key, label, pattern, phrases in CONDITION_GROUPS:
        codes = sorted(c for c, n in cond_names.items() if re.search(pattern, n, re.I) and not n.lower().startswith("suspected"))
        concepts.append({"key": f"cond:{key}", "kind": "condition", "label": label, "codes": codes, "phrases": phrases})
        grouped.update(codes)
    # one concept per condition name, even when the records code it in more than one system
    by_name: dict[str, list[str]] = defaultdict(list)
    for code, name in sorted(cond_names.items()):
        by_name[name].append(code)
    for name, codes in sorted(by_name.items(), key=lambda kv: kv[1][0]):
        concepts.append({"key": f"cond:{codes[0]}", "kind": "condition", "label": name, "codes": codes, "phrases": [norm(name)]})

    by_ingredient: dict[str, set[str]] = defaultdict(set)
    brand_of: dict[str, set[str]] = defaultdict(set)
    for code, name in med_names.items():
        ings = ingredients(name)
        for ing in ings:
            by_ingredient[ing].add(code)
        if len(ings) == 1:
            for b in brands(name):
                brand_of[ings[0]].add(b)
    for ing, codes in sorted(by_ingredient.items()):
        phrases = [ing] + sorted(brand_of[ing]) + MED_ALIASES.get(ing, [])
        if " " in ing and ing.split()[0] not in ("ethinyl", "insulin"):
            phrases.append(ing.split()[0])  # 'penicillin v' -> 'penicillin'
        concepts.append({"key": f"med:{ing.replace(' ', '_')}", "kind": "med", "label": ing.capitalize(), "codes": sorted(codes),
                         "phrases": sorted(set(p for p in phrases if p))})
    for key, label, members, phrases in MED_CLASSES:
        codes = sorted({c for ing, cs in by_ingredient.items() for c in cs if any(f" {m} " in f" {ing} " for m in members)})
        concepts.append({"key": f"medclass:{key}", "kind": "med", "label": label, "codes": codes, "phrases": phrases})

    for key, label, pattern, phrases in VACCINE_GROUPS:
        codes = sorted(c for c, n in vax_names.items() if re.search(pattern, n, re.I))
        concepts.append({"key": f"vax:{key}", "kind": "vaccine", "label": label, "codes": codes, "phrases": phrases})

    for code, name in sorted(allergy_names.items()):
        n = norm(name)
        phrases = [n] + ALLERGEN_ALIASES.get(n, [])
        if not ALLERGEN_ALIASES.get(n, True):  # 'Allergic disposition' is not an allergen
            continue
        concepts.append({"key": f"allergy:{code}", "kind": "allergy", "label": name, "codes": [code], "phrases": sorted(set(phrases))})

    for c in concepts:
        c["phrases"] = sorted({norm(p) for p in c["phrases"] if norm(p)}, key=lambda p: (-len(p), p))
    return {"version": 1, "concepts": concepts}
