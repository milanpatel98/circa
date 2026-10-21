import { useEffect, useMemo, useRef, useState } from "react";
import { Engine, fmtDate, yearsBetween } from "./rounds.js";

const REPO = "https://github.com/milanpatel98/rounds";
const KIND = { Observation: "Lab or vital", Condition: "Condition", MedicationRequest: "Medication order", AllergyIntolerance: "Allergy",
  Immunization: "Vaccine", Encounter: "Visit", Procedure: "Procedure" };
const NOTE = {
  answered: "",
  not_found: "Nothing in the record answers this.",
  unsupported: "This is outside what a patient record holds.",
  advice: "Rounds reports the record. It does not make treatment decisions.",
};
const LISTS = new Set(["med_list", "problem_list", "allergy_list", "vaccine_list"]);
const pct = (k, n) => `${(Math.round((k / n) * 1000) / 10).toFixed(1)}%`;
const TRY = [
  ["Last A1c", (p) => `What was ${p} last A1c?`],
  ["Current medications", (p, s) => `What medications is ${s} on?`],
  ["Allergies", () => "Any allergies?"],
  ["Blood pressure trend", (p) => `How has ${p} blood pressure changed?`],
  ["ER visits this year", () => "ER visits in the past year?"],
  ["Treatment advice", (p) => `Should we increase ${p} lisinopril?`],
];

export default function App() {
  const [meta, setMeta] = useState(null);
  const [lex, setLex] = useState(null);
  const [results, setResults] = useState(null);
  const [view, setView] = useState(() => location.hash.slice(1) || "ask");

  useEffect(() => {
    Promise.all(["patients", "lexicon", "results"].map((f) => fetch(`data/${f}.json`).then((r) => r.json()))).then(([p, l, r]) => {
      setMeta(p);
      setLex(l);
      setResults(r);
    });
    const onHash = () => setView(location.hash.slice(1) || "ask");
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);

  const engine = useMemo(() => (lex ? new Engine(lex) : null), [lex]);

  return (
    <div className="page">
      <header className="top">
        <a href="#" className={`brand ${view === "ask" ? "here" : ""}`}>Rounds</a>
        <nav>
          <a href="#results" className={view === "results" ? "here" : ""}>Results</a>
          <a href="#method" className={view === "method" ? "here" : ""}>Method</a>
          <a href={REPO}>Code</a>
        </nav>
      </header>

      <main>
        {view === "results" && results && meta ? <Results r={results} meta={meta} />
          : view === "method" ? <Method />
          : meta && engine ? <Ask meta={meta} engine={engine} /> : null}
      </main>

      <footer className="foot">© 2026 Milan Patel. MIT License. Synthetic patients only.</footer>
    </div>
  );
}

/* ---- ask -------------------------------------------------------------------------------- */

function Ask({ meta, engine }) {
  const [pid, setPid] = useState(meta.patients[0].id);
  const [picking, setPicking] = useState(false);
  const [file, setFile] = useState(null);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState(null);
  const [asked, setAsked] = useState("");
  const [sheet, setSheet] = useState(null); // id of the record to show, or "all"
  const pickRef = useRef(null);
  const inputRef = useRef(null);
  const patient = meta.patients.find((p) => p.id === pid);
  const first = patient.name.split(" ")[0];
  const poss = patient.sex === "female" ? "her" : "his";
  const subj = patient.sex === "female" ? "she" : "he";

  useEffect(() => {
    let live = true;
    setFile(null);
    setAnswer(null);
    setSheet(null);
    fetch(`data/p/${pid}.json`).then((r) => r.json()).then((f) => live && setFile(f));
    return () => {
      live = false;
    };
  }, [pid]);

  useEffect(() => {
    const close = (e) => pickRef.current && !pickRef.current.contains(e.target) && setPicking(false);
    const esc = (e) => e.key === "Escape" && (setSheet(null), setPicking(false));
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", esc);
    };
  }, []);

  const records = useMemo(() => (file ? Object.fromEntries(file.chart.records.map((r) => [r.id, r])) : {}), [file]);

  function run(text) {
    if (!file || !text.trim()) return;
    setAnswer(engine.ask(file.chart, text));
    setAsked(text.trim());
    setQ("");
    setSheet(null);
  }

  const sources = useMemo(() => {
    const out = [];
    const list = answer && LISTS.has(answer.intent) && answer.claims.length > 2;
    for (const c of (list ? answer.claims.slice(1).map((c) => ({ cites: c.cites.slice(0, 1) })) : answer?.claims) || []) {
      if (c.cites.length > 8) continue;
      for (const id of c.cites) if (!out.includes(id)) out.push(id);
    }
    return out;
  }, [answer]);

  return (
    <section className="ask">
      <div className="who" ref={pickRef}>
        <button className="who-name" onClick={() => setPicking((v) => !v)} aria-haspopup="listbox" aria-expanded={picking}>
          {patient.name}
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <p className="who-sub">
          {yearsBetween(patient.birthDate, meta.asOf)}, {patient.sex}. {patient.records.toLocaleString()} records up to {fmtDate(meta.asOf)}.
        </p>
        {picking && (
          <ul className="pick" role="listbox" aria-label="Choose a patient">
            {meta.patients.map((p) => (
              <li key={p.id}>
                <button role="option" aria-selected={p.id === pid} onClick={() => {
                  setPid(p.id);
                  setPicking(false);
                  inputRef.current?.focus();
                }}>
                  <span>{p.name}</span>
                  <span className="soft">{yearsBetween(p.birthDate, meta.asOf)}, {p.sex}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form className="q" onSubmit={(e) => {
        e.preventDefault();
        run(q);
      }}>
        <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Ask about ${first}`} aria-label="Question" disabled={!file} />
        <button type="submit" disabled={!file || !q.trim()}>Ask</button>
      </form>

      <p className="try">
        {TRY.map(([label, make], i) => (
          <span key={label}>
            <button onClick={() => run(make(poss, subj))} disabled={!file}>{label}</button>
            {i < TRY.length - 1 ? <span className="sep" aria-hidden="true">/</span> : null}
          </span>
        ))}
      </p>

      {answer && (
        <article className="said" aria-live="polite">
          <p className="asked">{asked}</p>
          {LISTS.has(answer.intent) && answer.claims.length > 2 ? (
            <>
              <p className="text">{answer.claims[0].text.replace(/:$/, ".")}</p>
              <ul className="items">
                {answer.claims.slice(1).map((c, i) => {
                  const n = sources.indexOf(c.cites[0]) + 1;
                  return (
                    <li key={i}>
                      <span>{c.text.replace(/[;.]$/, "")}</span>
                      {n > 0 && <button className={`cite ${sheet === sources[n - 1] ? "on" : ""}`} onClick={() => setSheet(sources[n - 1])} aria-label={`Show record ${n}`}>{n}</button>}
                    </li>
                  );
                })}
              </ul>
            </>
          ) : (
            <p className="text">
              {answer.claims.map((c, i) => (
                <span key={i}>
                  {c.text}
                  {c.cites.length > 0 && c.cites.length <= 8 && [...new Set(c.cites.map((id) => sources.indexOf(id) + 1))].map((n) => (
                    <button key={n} className={`cite ${sheet === sources[n - 1] ? "on" : ""}`} onClick={() => setSheet(sources[n - 1])}
                      aria-label={`Show record ${n}`}>{n}</button>
                  ))}{" "}
                </span>
              ))}
            </p>
          )}
          {NOTE[answer.status] && <p className="note">{NOTE[answer.status]}</p>}
          {sources.length > 0 && (
            <button className="records" onClick={() => setSheet("all")}>
              {sources.length === 1 ? "1 record cited" : `${sources.length} records cited`}, every number and date checked against them
            </button>
          )}
        </article>
      )}

      {sheet && file && (
        <Sheet ids={sources} focus={sheet === "all" ? null : sheet} records={records} raw={file.raw} chart={file.chart} onClose={() => setSheet(null)} />
      )}
    </section>
  );
}

function Sheet({ ids, focus, records, raw, chart, onClose }) {
  const [open, setOpen] = useState(focus);
  const panel = useRef(null);
  useEffect(() => setOpen(focus), [focus]);
  useEffect(() => panel.current?.focus(), []);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="sheet" role="dialog" aria-label="Cited records" tabIndex={-1} ref={panel}>
        <div className="sheet-head">
          <p>From {chart.name.split(" ")[0]}’s record</p>
          <button onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          </button>
        </div>
        <ol className="recs">
          {ids.map((id, i) => {
            const isPatient = id === chart.id;
            const r = records[id];
            const isOpen = open === id;
            return (
              <li key={id} className={isOpen ? "open" : ""}>
                <button className="rec" onClick={() => setOpen(isOpen ? null : id)} aria-expanded={isOpen}>
                  <span className="rec-n">{i + 1}</span>
                  <span className="rec-body">
                    <span className="rec-name">{isPatient ? chart.name : r?.name}</span>
                    <span className="soft">
                      {isPatient ? `Patient, born ${fmtDate(chart.birthDate)}` : `${KIND[r?.type] || "Record"}, ${fmtDate(r.date)}`}
                    </span>
                  </span>
                </button>
                {isOpen && (
                  <pre className="fhir">
                    {isPatient ? JSON.stringify({ resourceType: "Patient", id, gender: chart.sex, birthDate: chart.birthDate }, null, 2)
                      : raw?.[id] ? JSON.stringify(raw[id], null, 2) : "Not included in this demo."}
                  </pre>
                )}
              </li>
            );
          })}
        </ol>
        <p className="sheet-foot soft">Each record is shown exactly as it arrived, in FHIR, the format US health systems exchange.</p>
      </aside>
    </>
  );
}

/* ---- results ------------------------------------------------------------------------------ */

function Results({ r, meta }) {
  const [more, setMore] = useState(false);
  const H = (n) => r[n].by_split.heldout;
  const lines = [["Rounds", "rounds"], ["Search, reading the 20 closest records", "rag20"], ["Search, reading the 5 closest records", "rag5"]];
  const fails = ["latest", "med_active", "meds", "problems"];
  const label = Object.fromEntries(r.categories);
  return (
    <section className="prose">
      <h1>Right on {pct(H("rounds").correct, H("rounds").n)} of questions worded in ways it had never seen.</h1>
      <p className="lead">
        {r.questions.toLocaleString()} questions about {meta.cohort} synthetic patients, each checked against an answer key worked out separately from the
        record. Half were phrased by someone who never saw how Rounds reads questions; those are the scores below.
      </p>

      <div className="bars">
        {lines.map(([name, k]) => (
          <div key={k} className={`bar ${k === "rounds" ? "ours" : ""}`}>
            <span className="bar-name">{name}</span>
            <span className="bar-track"><span style={{ width: `${(H(k).correct / H(k).n) * 100}%` }} /></span>
            <span className="bar-v">{pct(H(k).correct, H(k).n)}</span>
          </div>
        ))}
      </div>
      <p className="soft small">
        Search is how most document assistants work: find the records that read most like the question, answer from those. It used the same vocabulary and
        answer logic as Rounds here, so the only difference is what it gets to read.
      </p>

      <h2>Where reading a few records goes wrong</h2>
      <p>
        “Latest” means newest, not most similar, and “current” needs the whole list. Search returned {H("rag20").wrong_answers} confidently wrong answers;
        Rounds returned {H("rounds").wrong_answers}, and declined rather than guessed on the rest of its misses.
      </p>
      <table className="t">
        <thead>
          <tr><th scope="col">Question</th><th scope="col">Rounds</th><th scope="col">Search, 20</th></tr>
        </thead>
        <tbody>
          {(more ? r.categories.map(([k]) => k).filter((k) => r.rounds.by_category[k]) : fails).map((k) => (
            <tr key={k}>
              <td>{label[k]}</td>
              <td>{Math.round(r.rounds.by_category[k].heldout * 100)}%</td>
              <td className="soft">{Math.round(r.rag20.by_category[k].heldout * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="link" onClick={() => setMore((m) => !m)}>{more ? "Show fewer" : "Show all 22 question types"}</button>

      <h2>How the number was kept honest</h2>
      <p>
        On the wording it was built with, Rounds scores {pct(r.rounds.by_split.dev.correct, r.rounds.by_split.dev.n)}, which says little. The first run on
        unseen wording scored {pct(r.first_run_heldout.correct, r.first_run_heldout.n)}. It turned up one bug, packaging words read as medicine names, and
        fixing only that gives {pct(H("rounds").correct, H("rounds").n)}. No question-reading rules changed after that wording was opened.
      </p>
    </section>
  );
}

/* ---- method ------------------------------------------------------------------------------- */

function Method() {
  return (
    <section className="prose">
      <h1>A chart answers questions. It should also show where each answer came from.</h1>
      <h2>The record</h2>
      <p>
        Patients are generated with Synthea and stored in FHIR, the format US hospitals exchange. Rounds reads labs, vitals, conditions, medication orders,
        allergies, vaccines and visits, and keeps the id of every record.
      </p>
      <h2>Reading the question</h2>
      <p>
        A vocabulary maps how clinicians talk to medical codes: A1c to its lab code, high blood pressure to hypertension, a statin to every statin ever
        ordered. No language model is involved. A question it cannot place is declined, not guessed at.
      </p>
      <h2>Answering</h2>
      <p>
        The answer is worked out over the whole chart, so latest means newest and current means still active. Every sentence carries the records it rests
        on, and a separate check confirms each number and date appears in them. The same check works on any answerer, including a language model.
      </p>
      <h2>Limits</h2>
      <p>Synthetic patients and structured fields only. Clinical notes are not read. Not for clinical use.</p>
    </section>
  );
}
