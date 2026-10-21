# Rounds

**Ask a patient's chart a question. Every sentence in the answer cites the FHIR record it came from, and a checker confirms the numbers and dates match.**

On hospital rounds, the senior doctor asks about a patient and the resident answers from the chart. "What was her last A1c?" "Is he still on the statin?" "Any ER visits this year?" Rounds answers those questions from a patient's FHIR record and shows the exact resource behind each sentence. If the chart has no answer, it says so. If the question asks for a treatment decision, it declines.

**[Try it in your browser](https://milanpatel98.github.io/rounds/)**: six synthetic patients, the full engine running client-side, and the original FHIR resource for every citation.

---

## Results

5,834 questions about 130 synthetic patients. Each question has an answer key computed from the record by separate code (`gold.py`). Each question is asked twice: once in wording written while the parser was built, and once in **held-out wording** written separately by someone who never saw the parser (`bench/heldout.json`).

| Answerer | Held-out wording | Confident wrong answers |
| --- | --- | --- |
| **Rounds** | **96.2%** (95% CI 95.4–96.8) | 40 of 2,917 |
| Search, top 20 records | 79.4% | 492 |
| Search, top 5 records | 65.6% | 875 |

"Search" is the usual retrieval-augmented approach: index each record as text, retrieve the records most similar to the question with BM25, and answer from those. To make the comparison about evidence and nothing else, the search baseline uses Rounds' own vocabulary for query expansion and Rounds' own answer logic. The only difference is that it reads k retrieved records instead of querying the whole chart.

Where retrieval breaks:

| Question type | Rounds | Search, top 20 | Search, top 5 |
| --- | --- | --- | --- |
| Latest result ("last A1c") | 100% | 79% | 26% |
| Trend | 100% | 73% | 18% |
| Current medication ("still on lisinopril?") | 100% | 46% | 32% |
| Medication list | 100% | 23% | 21% |
| Problem list | 88% | 22% | 9% |
| Last visit | 79% | 7% | 1% |

Similar is not the same as newest, and the top k records are not the whole list. A retriever returns the A1c results that best match the words, not the most recent one. It also returns an old lisinopril order marked `stopped`, without the active one, and states the patient is off it.

**On honesty of the numbers:** with the wording it was built against, Rounds scores 100%, which says little. On the held-out wording, the first run scored **95.9%**. That run exposed one vocabulary bug: packaging words in RxNorm names ("Auto-Injector", "28 Day Pack") were read as medicine names. Fixing only that gives 96.2%. No wording rules changed after the held-out set was opened, and `artifacts/heldout-first-run.json` keeps the first run. Of the 111 held-out misses, 71 were refusals ("the record does not cover that") rather than wrong answers.

## How it works

```
 Synthea  ──►  FHIR R4 bundles  ──►  chart (one list of records, each with its resource id)
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

**Real record format.** Patients come from [Synthea](https://github.com/synthetichealth/synthea), pinned to v3.3.0 with fixed seeds, exported as FHIR R4. Ingest keeps Observations (labs, vitals, smoking status), Conditions, MedicationRequests, AllergyIntolerances, Immunizations, Encounters and Procedures. It drops billing (Claim, ExplanationOfBenefit), and keeps social-circumstance findings (employment, education, housing) out of the problem list. Regenerating from scratch gives byte-identical charts.

**Vocabulary.** Labs and vitals map to LOINC by hand ("A1c", "kidney function" to eGFR, "bp"). Conditions, medications, vaccines and allergens are read from the records' own SNOMED, RxNorm and CVX codes, then grouped the way clinicians talk: "high blood pressure", "a statin", "blood thinner", "flu shot". The same vocabulary file drives Python and the browser.

**Parsing.** No model. The parser finds medical terms (longest match, with plural and one-typo tolerance), reads cue words outside those terms (so "allergic rhinitis" is not an allergy question), and works out the time frame ("in 2021", "past 12 months", "since 2020"). Anything it cannot place becomes `unsupported`, which is a refusal, not a guess.

**Answers carry citations.** Each sentence lists the record ids it rests on. "Latest" means newest by timestamp. "Current" means an active order or condition. Trends report direction from first to last of up to six points.

**The checker** (`verify.py`) works on any answerer's output. Every cited id must exist in the patient's record, and every number and date in a sentence must appear in the records it cites. It catches a language model that writes 6.4 when the record says 6.1, or cites a real record for a date it does not contain.

**Claude, optionally.** `rounds/llm.py` lets Claude answer the same benchmark. It reads the chart only through tools (`search`, `records`, `patient`) and must answer through a tool that requires citations. Then the same grader and checker score it:

```bash
export ANTHROPIC_API_KEY=...
rounds bench --answerer claude --limit 10
```

The browser runs a JavaScript port of the parser and engine. A test asks every benchmark question for the demo patients in both languages and requires identical answers.

## Run it

Requires Python 3.10+. The site needs Node 20+.

```bash
git clone https://github.com/milanpatel98/rounds.git
cd rounds
pip install -e ".[dev]"
pytest -q

rounds patients
rounds ask dane "what was his last a1c"
rounds ask dane "is he on a blood thinner"
rounds ask dane "should we increase his lisinopril"

rounds bench                      # Rounds, both wordings
rounds bench --answerer rag5      # the retrieval baseline
rounds bench --answerer rag20

cd web && npm install && npm run dev    # http://localhost:5181
```

To regenerate the patients from scratch (Java 17+, about two minutes): `./scripts/generate.sh && rounds ingest && rounds questions`.

## Project layout

```
rounds/fhir.py      FHIR bundle -> chart
rounds/lexicon.py   how clinicians say it -> LOINC / SNOMED / RxNorm / CVX
rounds/parse.py     question -> intent, concept, time frame
rounds/engine.py    query + chart -> cited answer
rounds/verify.py    checks any answer against the records it cites
rounds/rag.py       the BM25 retrieval baseline
rounds/llm.py       Claude as the answerer, through tools
rounds/gold.py      answer key, written separately from the engine
rounds/bench.py     question generation, grading, Wilson intervals
bench/heldout.json  held-out phrasings
data/               130 ingested charts and the vocabulary
web/                the site, with a JavaScript port of the engine
```

## Limitations

- The data is synthetic. Synthea is realistic in structure, not in every value. Some kidney patients have implausibly low A1c results, for example.
- Structured data only. Clinical notes are not read, and they are where much of a real chart lives.
- The parser covers the question types in the benchmark. Questions outside them are refused, not answered.
- Medication status comes from the order's status. Real records also need dispense and administration data to know what a patient actually takes.
- Not for clinical use.

## License

MIT. Synthea is Apache 2.0. All patients are synthetic.
