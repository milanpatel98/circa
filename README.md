# Circa

**Ask a patient's chart a question. Every sentence in the answer cites the FHIR record it came from, and a checker confirms the numbers and dates match.**

Clinicians ask a patient's chart the same questions every day. "What was her last A1c?" "Is he still on the statin?" "Any ER visits this year?" Circa answers those questions from a patient's FHIR record and shows the exact resource behind each sentence. If the chart has no answer, it says so. If the question asks for a treatment decision, it declines.

**[Try it in your browser](https://milanpatel98.github.io/circa/)**: all 100 real (de-identified) hospital patients, the full engine running client-side, and the original FHIR resource for every citation.

---

## Results

Two cohorts, both FHIR R4:

- **Real:** 100 de-identified patients from the [MIMIC-IV Clinical Database Demo on FHIR](https://physionet.org/content/mimic-iv-fhir-demo/2.1.0/) (Beth Israel Deaconess Medical Center), every clinical record in the release: 898,516 of them (a few thousand source entries are empty, such as a vital sign with no value, and are left out). Admissions, ED visits and ICU stays; diagnoses; medication orders, doses given, dispenses and home medications; procedures; labs and microbiology; ICU charting (vitals, assessments, outputs).
- **Synthetic:** 130 [Synthea](https://github.com/synthetichealth/synthea) patients, which add allergies, vaccines and outpatient visits that the hospital data does not have.

Every question has an answer key computed from the record by separate code (`gold.py`). Each is asked twice: in the wording written while the parser was built, and in **held-out wording** written separately by someone who never saw the parser (`bench/heldout.json`). Held-out scores:

| Answerer | Real patients (1,679 questions) | Wrong answers | Synthetic (2,917) | Wrong answers |
| --- | --- | --- | --- | --- |
| **Circa** | **97.8%** (95% CI 97.0–98.4) | **4** | **96.2%** (95.4–96.8) | **40** |
| Search, top 20 records | 66.1% | 481 | 79.4% | 492 |
| Search, top 5 records | 58.4% | 567 | 65.6% | 875 |

"Search" is the usual retrieval-augmented approach: index each record as text, retrieve the records most similar to the question with BM25, and answer from those. To make the comparison about evidence and nothing else, the search baseline uses Circa's own vocabulary for query expansion and Circa's own answer logic. The only difference is that it reads k retrieved records instead of querying the whole chart.

Where retrieval breaks, on real patients:

| Question type | Circa | Search, top 20 | Search, top 5 |
| --- | --- | --- | --- |
| Latest result ("last A1c") | 100% | 51% | 21% |
| Trend | 100% | 41% | 8% |
| Current medication ("still on heparin?") | 100% | 85% | 82% |
| Stopped medication | 100% | 13% | 0% |
| Medication list | 100% | 0% | 0% |
| Problem list | 93% | 0% | 0% |
| ER visits in a period | 100% | 47% | 47% |
| Last visit | 85% | 34% | 28% |

Similar is not the same as newest, and the top k records are not the whole list. A real hospital stay can carry 40 medication orders and 30 diagnoses; 20 retrieved records cannot list them. More data makes search worse, not better: one ICU patient has 50,306 records, and adding the ICU charting dropped search from 70.3% to 66.1% while Circa held steady.

**Hospital records mean different things.** MIMIC diagnoses are billing codes attached to a stay, with no onset or resolved date, so Circa says "recorded at the hospital stay of …" rather than "active". Every medication order is completed by discharge, so "current medications" means those ordered during the most recent stay, and the answer says so. Dates are shifted into the 2100s for privacy; each patient's "today" is their latest record.

**On honesty of the numbers:** with the wording it was built against, Circa scores 100% on both cohorts, which says little.

- *Synthetic:* the first held-out run scored **95.9%**. It exposed one vocabulary bug: packaging words in RxNorm names ("Auto-Injector", "28 Day Pack") were read as medicine names. Fixing only that gives 96.2%. `artifacts/heldout-first-run.json` keeps the first run.
- *Real:* the first held-out run scored **95.3%** (40 wrong answers). Two parser gaps caused most misses: years in the shifted 2100s were not read as years, and "currently on glucose" was read as the glucose lab rather than the medicine. Fixing those gives 97.3%. Both fixes came after the synthetic held-out set had been opened; they leave its score unchanged.
- *All records:* adding the ICU, medication-administration, procedure and microbiology records (from 118,869 to 898,516 records) changed which lab and vital questions get asked, so the benchmark was regenerated. Its first run scored 97.2% with no parser change; ICU blood pressure, heart rate, temperature and weight questions were added to the vocabulary before the run. An audit then found 11,000 medication records whose names sit in another field (IV mixes, formulary codes) and 12,000 text lab results ("<0.01", "NEG") that were not being read. Reading them gives 97.8%.

No held-out phrasing was edited after it was opened.

## How it works

```
 MIMIC / Synthea  ──►  FHIR R4  ──►  chart (one list of records, each with its resource id)
                                          │
 "is he still on a statin?"               │
        │                                 ▼
        ├─► parse ──► {intent: on_med, concept: statin → 9 RxNorm codes}
        │                                 │
        │                          engine: query the whole chart
        │                                 │
        ▼                                 ▼
   answer, sentence by sentence, each with the ids it rests on  ──►  checker
```

**Real record format.** Real patients come from MIMIC-IV's FHIR export. `circa/mimic.py` reads every clinical file in it: Encounter (hospital, ED, ICU), Condition, MedicationRequest, MedicationAdministration, MedicationDispense, MedicationStatement, Procedure, and Observations for labs, microbiology, ED vitals and ICU charting. ICU blood pressure arrives as separate systolic and diastolic items; readings charted at the same minute are paired, and the citation shows both original resources. Only reference data (Location, Organization, Specimen) is left out. Synthetic patients come from [Synthea](https://github.com/synthetichealth/synthea), pinned to v3.3.0 with fixed seeds, exported as FHIR R4. Ingest keeps Observations (labs, vitals, smoking status), Conditions, MedicationRequests, AllergyIntolerances, Immunizations, Encounters and Procedures. It drops billing (Claim, ExplanationOfBenefit), and keeps social-circumstance findings (employment, education, housing) out of the problem list. Regenerating from scratch gives byte-identical charts.

**Vocabulary.** Labs and vitals map to LOINC (and MIMIC's lab item ids) by hand ("A1c", "kidney function" to eGFR, "bp"). Conditions, medications, vaccines and allergens are read from the records' own SNOMED, RxNorm and CVX codes, then grouped the way clinicians talk: "high blood pressure", "a statin", "blood thinner", "flu shot". The same vocabulary file drives Python and the browser.

**Parsing.** No model. The parser finds medical terms (longest match, with plural and one-typo tolerance), reads cue words outside those terms (so "allergic rhinitis" is not an allergy question), and works out the time frame ("in 2021", "past 12 months", "since 2020"). Anything it cannot place becomes `unsupported`, which is a refusal, not a guess.

**Answers carry citations.** Each sentence lists the record ids it rests on. "Latest" means newest by timestamp. "Current" means an active order or condition. Trends report direction from first to last of up to six points.

**The checker** (`verify.py`) works on any answerer's output. Every cited id must exist in the patient's record, and every number and date in a sentence must appear in the records it cites. It catches a language model that writes 6.4 when the record says 6.1, or cites a real record for a date it does not contain.

**Claude, optionally.** `circa/llm.py` lets Claude answer the same benchmark. It reads the chart only through tools (`search`, `records`, `patient`) and must answer through a tool that requires citations. Then the same grader and checker score it:

```bash
export ANTHROPIC_API_KEY=...
circa bench --answerer claude --limit 10
```

The browser runs a JavaScript port of the parser and engine. A test asks every benchmark question for the demo patients in both languages and requires identical answers.

## Run it

Requires Python 3.10+. The site needs Node 20+.

```bash
git clone https://github.com/milanpatel98/circa.git
cd circa
pip install -e ".[dev]"
pytest -q

circa patients
circa ask dane "what was his last a1c"
circa ask dane "is he on a blood thinner"
circa ask dane "should we increase his lisinopril"

circa bench                      # Circa, both wordings
circa bench --answerer rag5      # the retrieval baseline
circa bench --answerer rag20
circa --data real bench          # the same on the 100 real patients

cd web && npm install && npm run dev    # http://localhost:5181
```

The MIMIC-IV demo release is included as published in `mimic/fhir/` (about 50 MB, ODbL). Build the 100 real charts with `circa --data real ingest mimic/fhir` (about a minute) before running the real-patient tests or `circa export`.

To regenerate the synthetic patients from scratch (Java 17+, about two minutes): `./scripts/generate.sh && circa ingest && circa questions`.

## Project layout

```
circa/fhir.py      FHIR bundle -> chart (Synthea)
circa/mimic.py     MIMIC-IV FHIR NDJSON -> chart (real patients)
circa/lexicon.py   how clinicians say it -> LOINC / SNOMED / RxNorm / CVX
circa/parse.py     question -> intent, concept, time frame
circa/engine.py    query + chart -> cited answer
circa/verify.py    checks any answer against the records it cites
circa/rag.py       the BM25 retrieval baseline
circa/llm.py       Claude as the answerer, through tools
circa/gold.py      answer key, written separately from the engine
circa/bench.py     question generation, grading, Wilson intervals
bench/heldout.json  held-out phrasings
data/               130 synthetic charts and both vocabularies (real charts are built from mimic/)
mimic/fhir/         the MIMIC-IV Demo on FHIR release, unchanged
web/                the site, with a JavaScript port of the engine
```

## Limitations

- The real cohort is 100 patients from one hospital, and only its hospital stays: no outpatient visits, allergies or vaccines. "Current medications" means orders from the most recent stay; doses given are shown in the record but not yet asked about. Those question types are tested on synthetic data only.
- Structured data only. Clinical notes are not read, and they are where much of a real chart lives.
- The parser covers the question types in the benchmark. Questions outside them are refused, not answered.
- Medication status comes from the order's status. Real records also need dispense and administration data to know what a patient actually takes.
- Not for clinical use.

## License

Code: MIT. Real patient data: MIMIC-IV Clinical Database Demo on FHIR v2.1.0 (PhysioNet), Open Database License v1.0; the charts built from it are a derived database under the same license. Synthea is Apache 2.0.
