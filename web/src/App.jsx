import { useEffect, useMemo, useRef, useState } from "react";
import { Engine, fmtDate, yearsBetween } from "./rounds.js";

const REPO = "https://github.com/milanpatel98/rounds";
const STATUS = { answered: "Answered", not_found: "Not in the record", unsupported: "Outside the record", advice: "Declined: treatment advice" };
const TYPE = { Observation: "Observation", Condition: "Condition", MedicationRequest: "Medication order", AllergyIntolerance: "Allergy",
  Immunization: "Immunization", Encounter: "Visit", Procedure: "Procedure" };
const pct = (x) => `${Math.round(x * 1000) / 10}%`;
const whole = (x) => `${Math.round(x * 100)}%`;

export default function App() {
  const [meta, setMeta] = useState(null);
  const [lex, setLex] = useState(null);
  const [results, setResults] = useState(null);

  useEffect(() => {
    Promise.all(["patients", "lexicon", "results"].map((f) => fetch(`data/${f}.json`).then((r) => r.json()))).then(([p, l, r]) => {
      setMeta(p);
      setLex(l);
      setResults(r);
    });
  }, []);

  const engine = useMemo(() => (lex ? new Engine(lex) : null), [lex]);

  return (
    <>
      <div className="band">
        <header className="bar wrap">
          <a className="brand" href="#top">
            <span className="mark" aria-hidden="true" />
            Rounds
          </a>
          <nav>
            <a href="#results">Results</a>
            <a href="#how">How it works</a>
            <a href={REPO}>Source</a>
          </nav>
        </header>
        <section className="hero wrap" id="top">
          <h1>Ask a patient’s chart. Every answer shows where it came from.</h1>
          <p className="lede">
            Questions about a medical record, answered from its FHIR data. Each sentence links to the record behind it, and when the chart is silent, so is
            Rounds.
          </p>
        </section>
      </div>
      <main>
        <div className="wrap">{meta && engine ? <Desk meta={meta} engine={engine} /> : <div className="desk desk-loading" />}</div>
        {results && <Results r={results} meta={meta} />}
        <How />
      </main>
      <footer className="foot wrap">
        <span>© 2026 Milan Patel · <a href={`${REPO}/blob/main/LICENSE`}>MIT License</a></span>
        <span>Synthetic patients only. Not for clinical use.</span>
      </footer>
    </>
  );
}

/* ---- the ask desk ---------------------------------------------------------------------- */

function Desk({ meta, engine }) {
  const [pid, setPid] = useState(meta.patients[0].id);
  const [file, setFile] = useState(null);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState(null);
  const [asked, setAsked] = useState("");
  const [sel, setSel] = useState(null);
  const [ms, setMs] = useState(0);
  const input = useRef(null);
  const patient = meta.patients.find((p) => p.id === pid);

  useEffect(() => {
    let live = true;
    setFile(null);
    setAnswer(null);
    setSel(null);
    fetch(`data/p/${pid}.json`).then((r) => r.json()).then((f) => live && setFile(f));
    return () => {
      live = false;
    };
  }, [pid]);

  useEffect(() => {
    if (file && !answer) ask(patient.suggest[0]);
  }, [file]); // eslint-disable-line react-hooks/exhaustive-deps

  const records = useMemo(() => (file ? Object.fromEntries(file.chart.records.map((r) => [r.id, r])) : {}), [file]);

  function ask(text) {
    if (!file || !text.trim()) return;
    const t0 = performance.now();
    const a = engine.ask(file.chart, text);
    setMs(performance.now() - t0);
    setAnswer(a);
    setAsked(text);
    setQ("");
    const first = a.claims.flatMap((c) => c.cites)[0];
    setSel(first && records[first] ? first : first === file.chart.id ? first : null);
  }

  // number each cited record once, in order of first appearance
  const order = useMemo(() => {
    const m = new Map();
    for (const c of answer?.claims || []) for (const id of c.cites) if (!m.has(id)) m.set(id, m.size + 1);
    return m;
  }, [answer]);

  const age = yearsBetween(patient.birthDate, meta.asOf);
  return (
    <section className="desk" aria-label="Ask a question">
      <div className="patients" role="tablist" aria-label="Patients">
        {meta.patients.map((p) => (
          <button key={p.id} role="tab" aria-selected={p.id === pid} className={`pt ${p.id === pid ? "on" : ""}`} onClick={() => setPid(p.id)}>
            <span className="pt-name">{p.name}</span>
            <span className="pt-sub">
              {p.sex === "female" ? "F" : "M"} · {yearsBetween(p.birthDate, meta.asOf)} · {p.records.toLocaleString()} records
            </span>
          </button>
        ))}
      </div>

      <div className="desk-body">
        <div className="ask">
          <form
            className="ask-form"
            onSubmit={(e) => {
              e.preventDefault();
              ask(q);
            }}
          >
            <input
              ref={input}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={`Ask about ${patient.name.split(" ")[0]}, ${age}…`}
              aria-label="Question"
              disabled={!file}
            />
            <button type="submit" disabled={!file || !q.trim()}>
              Ask
            </button>
          </form>
          <div className="chips">
            {patient.suggest.map((s) => (
              <button key={s} className="chip" onClick={() => ask(s)} disabled={!file}>
                {s}
              </button>
            ))}
          </div>

          <div className="answer" aria-live="polite">
            {!answer ? (
              <p className="muted">{file ? "" : "Loading the record…"}</p>
            ) : (
              <>
                <p className="asked">{asked}</p>
                <p className={`status st-${answer.status}`}>{STATUS[answer.status]}</p>
                <div className="claims">
                  {answer.claims.map((c, i) => (
                    <span key={i} className="claim">
                      {c.text}
                      {c.cites.length > 0 && c.cites.length <= 8 &&
                        c.cites.map((id) => (
                          <button key={id} className={`cite ${sel === id ? "on" : ""}`} onClick={() => setSel(id)} title="Show the source record">
                            {order.get(id)}
                          </button>
                        ))}
                      {c.cites.length > 8 && (
                        <button className={`cite cite-wide ${sel === c.cites[0] ? "on" : ""}`} onClick={() => setSel(c.cites[0])}>
                          {c.cites.length} records
                        </button>
                      )}{" "}
                    </span>
                  ))}
                </div>
                <p className="check">
                  {answer.claims.some((c) => c.cites.length)
                    ? `Every number and date above is checked against the records it cites · ${ms < 1 ? "<1" : Math.round(ms)} ms`
                    : `Nothing cited, because nothing was claimed · ${ms < 1 ? "<1" : Math.round(ms)} ms`}
                </p>
              </>
            )}
          </div>
        </div>

        <Source id={sel} rec={records[sel]} raw={file?.raw?.[sel]} chart={file?.chart} />
      </div>
    </section>
  );
}

function Source({ id, rec, raw, chart }) {
  if (!id) {
    return (
      <aside className="source empty">
        <p className="src-label">Source</p>
        <p className="muted">Pick a number in the answer to see the record it came from.</p>
      </aside>
    );
  }
  if (chart && id === chart.id) {
    return (
      <aside className="source">
        <p className="src-label">Source · Patient</p>
        <p className="src-title">{chart.name}</p>
        <p className="src-meta">Born {fmtDate(chart.birthDate)} · {chart.sex}</p>
      </aside>
    );
  }
  return (
    <aside className="source">
      <p className="src-label">Source · {TYPE[rec?.type] || "Record"}</p>
      <p className="src-title">{rec?.name}</p>
      <p className="src-meta">
        {rec ? fmtDate(rec.date) : ""}
        {rec?.status ? ` · ${rec.status}` : ""}
        {rec?.code ? ` · ${rec.system.toUpperCase()} ${rec.code}` : ""}
      </p>
      <p className="src-label src-gap">FHIR resource</p>
      <pre className="json">{raw ? JSON.stringify(raw, null, 2) : "Not included in this demo."}</pre>
    </aside>
  );
}

/* ---- results ---------------------------------------------------------------------------- */

function Results({ r, meta }) {
  const H = (name) => r[name]?.by_split.heldout;
  const rows = r.categories.filter(([k]) => r.rounds.by_category[k]);
  return (
    <section id="results" className="results wrap">
      <div className="sec-head">
        <h2>Results</h2>
        <p>
          {r.questions.toLocaleString()} questions about {meta.cohort} synthetic patients, each with an answer key computed separately from the record.
          Every question is asked in wording written by someone who never saw the parser.
        </p>
      </div>
      <div className="big">
        <Stat value={pct(H("rounds").correct / H("rounds").n)} label="Rounds" note={`${H("rounds").wrong_answers} confident wrong answers; the rest of its misses were refusals`} strong />
        <Stat value={pct(H("rag20").correct / H("rag20").n)} label="Search, top 20 records" note={`${H("rag20").wrong_answers} confident wrong answers`} />
        <Stat value={pct(H("rag5").correct / H("rag5").n)} label="Search, top 5 records" note={`${H("rag5").wrong_answers} confident wrong answers`} />
      </div>
      <p className="fine">
        “Search” is the usual approach: retrieve the records most similar to the question, then answer from those. Here it uses the same vocabulary and the
        same answer logic as Rounds, so the only difference is what it gets to read.
      </p>
      <div className="table-scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th scope="col">Question type</th>
              <th scope="col">Rounds</th>
              <th scope="col">Search, top 20</th>
              <th scope="col">Search, top 5</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([k, label]) => (
              <tr key={k}>
                <td>{label}</td>
                {["rounds", "rag20", "rag5"].map((n) => (
                  <td key={n}>
                    <Bar v={r[n].by_category[k].heldout} strong={n === "rounds"} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="fine">
        With the wording it was built against, Rounds scores {pct(r.rounds.by_split.dev.accuracy)}. On the hidden wording, the first run scored{" "}
        {pct(r.first_run_heldout.accuracy)}; it exposed one vocabulary bug (packaging words read as medicine names), and fixing only that gives{" "}
        {pct(H("rounds").correct / H("rounds").n)}. No wording rules changed after the hidden set was opened.
      </p>
    </section>
  );
}

function Stat({ value, label, note, strong }) {
  return (
    <div className={`stat ${strong ? "stat-strong" : ""}`}>
      <p className="stat-v">{value}</p>
      <p className="stat-l">{label}</p>
      <p className="stat-n">{note}</p>
    </div>
  );
}

function Bar({ v, strong }) {
  return (
    <span className={`bar-cell ${strong ? "strong" : ""}`}>
      <span className="bar-track">
        <span style={{ width: `${Math.max(1.5, v * 100)}%` }} />
      </span>
      <span className="bar-v">{whole(v)}</span>
    </span>
  );
}

/* ---- how it works ---------------------------------------------------------------------- */

function How() {
  const items = [
    ["Real record format", "Patients are generated with Synthea and stored as FHIR R4, the standard US health systems exchange. Rounds reads labs, vitals, conditions, medication orders, allergies, immunizations and visits, and keeps every resource id."],
    ["Questions become queries", "A vocabulary maps how clinicians talk to codes: “high blood pressure” to SNOMED, “A1c” to LOINC, “a statin” to every simvastatin and atorvastatin order. The question becomes a typed query over the whole chart, with its time frame."],
    ["Answers cite, then get checked", "Each sentence carries the ids of the records it rests on. A separate checker confirms every number and date appears in those records. Any answerer can be checked this way, including a language model."],
    ["Refusing is an answer", "If a lab was never done, Rounds says so. If the question asks for a treatment decision or something a record cannot hold, it declines instead of guessing."],
  ];
  return (
    <section id="how" className="how wrap">
      <div className="sec-head">
        <h2>How it works</h2>
      </div>
      <ol className="how-list">
        {items.map(([t, d], i) => (
          <li key={t}>
            <span className="how-n">{String(i + 1).padStart(2, "0")}</span>
            <h3>{t}</h3>
            <p>{d}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
