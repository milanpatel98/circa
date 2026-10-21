import { useEffect, useMemo, useRef, useState } from "react";
import { Engine, fmtDate, yearsBetween } from "./rounds.js";

const NAME = "Circa";

const KIND = { Observation: "Lab or vital", Condition: "Condition", MedicationRequest: "Medication order", AllergyIntolerance: "Allergy",
  Immunization: "Vaccine", Encounter: "Visit", Procedure: "Procedure" };
const STATUS = { answered: "Answered", not_found: "Not in record", unsupported: "Outside record", advice: "Declined" };
const LISTS = new Set(["med_list", "problem_list", "allergy_list", "vaccine_list"]);
const pct = (k, n) => `${(Math.round((k / n) * 1000) / 10).toFixed(1)}%`;
const brand = (s) => s.replace(/\bRounds\b/g, NAME);

/* Categories and their one-tap questions. p = his/her, s = he/she. */
const CATS = [
  ["labs", "Labs", [
    ["Last A1c", (p) => `What was ${p} last A1c?`],
    ["Blood pressure trend", (p) => `How has ${p} blood pressure changed?`],
    ["Latest LDL", (p) => `What was ${p} last LDL?`],
    ["Weight over time", (p) => `How has ${p} weight changed?`],
  ]],
  ["meds", "Medications", [
    ["Current medications", (p, s) => `What medications is ${s} on?`],
    ["On a blood thinner?", (p, s) => `Is ${s} on a blood thinner?`],
    ["On a statin?", (p, s) => `Is ${s} on a statin?`],
    ["When started lisinopril", (p, s) => `When did ${s} start lisinopril?`],
    ["Treatment question", (p) => `Should we increase ${p} lisinopril?`],
  ]],
  ["conditions", "Conditions", [
    ["Problem list", (p) => `What are ${p} active problems?`],
    ["Diabetes?", (p, s) => `Does ${s} have diabetes?`],
    ["Hypertension?", (p, s) => `Does ${s} have hypertension?`],
    ["Asthma?", (p, s) => `Does ${s} have asthma?`],
  ]],
  ["allergies", "Allergies", [
    ["All allergies", () => "Any allergies?"],
    ["Penicillin?", (p, s) => `Is ${s} allergic to penicillin?`],
    ["Peanuts?", (p, s) => `Is ${s} allergic to peanuts?`],
  ]],
  ["vaccines", "Vaccines", [
    ["Last flu shot", (p) => `When was ${p} last flu shot?`],
    ["COVID vaccine", (p) => `When was ${p} last covid vaccine?`],
    ["Tetanus", (p) => `When was ${p} last tetanus shot?`],
  ]],
  ["visits", "Visits", [
    ["Last visit", (p, s) => `When was ${s} last seen?`],
    ["ER visits this year", () => "How many ER visits in the past year?"],
    ["Age", (p, s) => `How old is ${s}?`],
  ]],
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
  const tabs = [["ask", "Ask", "#"], ["results", "Results", "#results"], ["method", "Method", "#method"]];

  return (
    <div className="page">
      <header className="top">
        <a href="#" className="brand">{NAME}</a>
        <nav className="nav" aria-label="Section">
          {tabs.map(([k, label, href]) => (
            <a key={k} href={href} className={view === k ? "on" : ""} aria-current={view === k ? "page" : undefined}>{label}</a>
          ))}
        </nav>
      </header>

      <main>
        {view === "results" && results && meta ? <Results r={results} meta={meta} />
          : view === "method" ? <Method />
          : meta && engine ? <Ask meta={meta} engine={engine} /> : null}
      </main>

      <footer className="foot">© 2026 Milan Patel · MIT License</footer>
    </div>
  );
}

/* ---- ask -------------------------------------------------------------------------------- */

function Ask({ meta, engine }) {
  const [pid, setPid] = useState(meta.patients[0].id);
  const [picking, setPicking] = useState(false);
  const [file, setFile] = useState(null);
  const [cat, setCat] = useState("labs");
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

  const isList = answer && LISTS.has(answer.intent) && answer.claims.length > 2;
  const sources = useMemo(() => {
    const out = [];
    for (const c of (isList ? answer.claims.slice(1).map((c) => ({ cites: c.cites.slice(0, 1) })) : answer?.claims) || []) {
      if (c.cites.length > 8) continue;
      for (const id of c.cites) if (!out.includes(id)) out.push(id);
    }
    return out;
  }, [answer, isList]);

  const Mark = ({ id }) => {
    const n = sources.indexOf(id) + 1;
    if (!n) return null;
    return <button className={`cite ${sheet === id ? "on" : ""}`} onClick={() => setSheet(id)} aria-label={`Record ${n}`}>{n}</button>;
  };

  const questions = CATS.find(([k]) => k === cat)[2];

  return (
    <section className="ask">
      <div className="who" ref={pickRef}>
        <button className="who-name" onClick={() => setPicking((v) => !v)} aria-haspopup="listbox" aria-expanded={picking}>
          {patient.name}
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
        </button>
        <p className="who-sub">{yearsBetween(patient.birthDate, meta.asOf)}, {patient.sex}</p>
        {picking && (
          <ul className="pick" role="listbox" aria-label="Choose a patient">
            {meta.patients.map((p) => (
              <li key={p.id}>
                <button role="option" aria-selected={p.id === pid} onClick={() => {
                  setPid(p.id);
                  setPicking(false);
                }}>
                  <span>{p.name}</span>
                  <span className="soft">{yearsBetween(p.birthDate, meta.asOf)}, {p.sex}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="index">
        <div className="cats" role="tablist" aria-label="Category">
          {CATS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={cat === k} className={`cat ${cat === k ? "on" : ""}`} onClick={() => setCat(k)}>{label}</button>
          ))}
        </div>
        <div className="qs" role="tabpanel">
          {questions.map(([label, make]) => (
            <button key={label} className="qb" onClick={() => run(make(poss, subj))} disabled={!file}>{label}</button>
          ))}
        </div>
      </div>

      <form className="q" onSubmit={(e) => {
        e.preventDefault();
        run(q);
      }}>
        <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Ask anything about ${first}`} aria-label="Question" disabled={!file} />
        <button type="submit" className="primary" disabled={!file || !q.trim()}>Ask</button>
      </form>

      {answer && (
        <article className="said" aria-live="polite">
          <div className="said-head">
            <p className="asked">{asked}</p>
            <span className={`tag ${answer.status}`}>{STATUS[answer.status]}</span>
          </div>
          {isList ? (
            <>
              <p className="text">{answer.claims[0].text.replace(/:$/, ".")}</p>
              <ul className="rows">
                {answer.claims.slice(1).map((c, i) => (
                  <li key={i}>
                    <span>{c.text.replace(/[;.]$/, "")}</span>
                    <Mark id={c.cites[0]} />
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text">
              {answer.claims.map((c, i) => (
                <span key={i}>
                  {brand(c.text)}
                  {c.cites.length > 0 && c.cites.length <= 8 && c.cites.map((id) => <Mark key={id} id={id} />)}{" "}
                </span>
              ))}
            </p>
          )}
          {sources.length > 0 && (
            <button className="ghost" onClick={() => setSheet("all")}>View {sources.length === 1 ? "1 record" : `${sources.length} records`}</button>
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
          <p>Records</p>
          <button onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" /></svg>
          </button>
        </div>
        <ol className="recs">
          {ids.map((id, i) => {
            const isPatient = id === chart.id;
            const r = records[id];
            const isOpen = open === id;
            return (
              <li key={id}>
                <button className="rec" onClick={() => setOpen(isOpen ? null : id)} aria-expanded={isOpen}>
                  <span className={`cite ${isOpen ? "on" : ""}`} aria-hidden="true">{i + 1}</span>
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
      </aside>
    </>
  );
}

/* ---- results ------------------------------------------------------------------------------ */

function Results({ r, meta }) {
  const [more, setMore] = useState(false);
  const H = (n) => r[n].by_split.heldout;
  const lines = [[NAME, "rounds"], ["Search, top 20", "rag20"], ["Search, top 5", "rag5"]];
  const keys = more ? r.categories.map(([k]) => k).filter((k) => r.rounds.by_category[k]) : ["latest", "med_active", "meds", "problems"];
  const label = Object.fromEntries(r.categories);
  return (
    <section className="results">
      <p className="big">{pct(H("rounds").correct, H("rounds").n)}</p>
      <p className="caption">correct on unseen wording</p>
      <p className="soft note">
        {H("rounds").n.toLocaleString()} held-out questions, {meta.cohort} synthetic patients. Search answers from the records most like the question; {NAME} reads the whole chart.
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

      <table className="t">
        <thead>
          <tr><th scope="col">Question type</th><th scope="col">{NAME}</th><th scope="col">Search, top 20</th></tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k}>
              <td>{label[k]}</td>
              <td>{Math.round(r.rounds.by_category[k].heldout * 100)}%</td>
              <td className="soft">{Math.round(r.rag20.by_category[k].heldout * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="ghost" onClick={() => setMore((m) => !m)} aria-expanded={more}>{more ? "Show fewer" : `Show all ${r.categories.length}`}</button>
    </section>
  );
}

/* ---- method ------------------------------------------------------------------------------- */

function Method() {
  const rows = [
    ["Record", "Synthetic FHIR patients from Synthea: labs, vitals, conditions, medications, allergies, vaccines and visits, each kept with its id."],
    ["Question", "A clinical vocabulary maps everyday wording to codes; no language model, and anything it cannot place is declined."],
    ["Answer", "Worked out over the whole chart, so latest means newest and current means still active; every sentence cites its records."],
    ["Limits", "Structured fields only, no clinical notes, not for clinical use."],
  ];
  return (
    <section className="method">
      <div className="grid">
        {rows.map(([t, s]) => (
          <div key={t} className="cell">
            <h2>{t}</h2>
            <p>{s}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
