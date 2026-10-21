import { useEffect, useMemo, useRef, useState } from "react";
import { Engine, fmtDate, yearsBetween } from "./rounds.js";

const REPO = "https://github.com/milanpatel98/rounds";
const STATUS = { answered: "Answered", not_found: "Not in the record", unsupported: "Outside the record", advice: "Declined" };
const TYPE = { Observation: "Observation", Condition: "Condition", MedicationRequest: "Medication", AllergyIntolerance: "Allergy",
  Immunization: "Immunization", Encounter: "Visit", Procedure: "Procedure" };
const pct1 = (k, n) => `${(Math.round((k / n) * 1000) / 10).toFixed(1)}%`;
const whole = (x) => `${Math.round(x * 100)}`;

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("rounds-theme") || "dark";
    } catch {
      return "dark";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("rounds-theme", theme);
    } catch {
      /* private mode */
    }
  }, [theme]);
  return [theme, setTheme];
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [lex, setLex] = useState(null);
  const [results, setResults] = useState(null);
  const [tab, setTab] = useState(() => (location.hash === "#results" ? "results" : location.hash === "#how" ? "how" : "ask"));
  const [theme, setTheme] = useTheme();

  useEffect(() => {
    Promise.all(["patients", "lexicon", "results"].map((f) => fetch(`data/${f}.json`).then((r) => r.json()))).then(([p, l, r]) => {
      setMeta(p);
      setLex(l);
      setResults(r);
    });
  }, []);
  useEffect(() => {
    history.replaceState(null, "", tab === "ask" ? location.pathname : `#${tab}`);
  }, [tab]);

  const engine = useMemo(() => (lex ? new Engine(lex) : null), [lex]);

  return (
    <div className="app">
      <header className="top">
        <span className="brand">
          <span className="ring" aria-hidden="true" />
          Rounds
        </span>
        <div className="top-r">
          <span className="mono dim hide-sm">{meta ? `AS OF ${fmtDate(meta.asOf).toUpperCase()}` : ""}</span>
          <div className="seg" role="group" aria-label="Appearance">
            <button aria-pressed={theme === "dark"} className={theme === "dark" ? "on" : ""} onClick={() => setTheme("dark")} title="Dark">
              <Moon />
            </button>
            <button aria-pressed={theme === "light"} className={theme === "light" ? "on" : ""} onClick={() => setTheme("light")} title="Light">
              <Sun />
            </button>
          </div>
        </div>
      </header>

      <main className="col">
        <h1>{tab === "ask" ? "Ask" : tab === "results" ? "Results" : "How it works"}</h1>
        <p className="sub">Answers from a patient’s FHIR record. Every sentence cites the record it came from.</p>
        <nav className="tabs" role="tablist">
          {[["ask", "Ask"], ["results", "Results"], ["how", "How it works"]].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
              {l}
            </button>
          ))}
        </nav>

        {tab === "ask" && (meta && engine ? <Ask meta={meta} engine={engine} /> : <p className="dim pad">Loading…</p>)}
        {tab === "results" && results && <Results r={results} meta={meta} />}
        {tab === "how" && <How />}
      </main>

      <footer className="foot col">
        <span>© 2026 Milan Patel · MIT License</span>
        <a href={REPO}>Source</a>
      </footer>
    </div>
  );
}

/* ---- ask ------------------------------------------------------------------------------- */

function Ask({ meta, engine }) {
  const [pid, setPid] = useState(meta.patients[0].id);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState(null);
  const [asked, setAsked] = useState("");
  const [expanded, setExpanded] = useState(null);
  const [ms, setMs] = useState(0);
  const menu = useRef(null);
  const patient = meta.patients.find((p) => p.id === pid);

  useEffect(() => {
    let live = true;
    setFile(null);
    setAnswer(null);
    fetch(`data/p/${pid}.json`).then((r) => r.json()).then((f) => live && setFile(f));
    return () => {
      live = false;
    };
  }, [pid]);

  useEffect(() => {
    if (file && !answer) run(patient.suggest[0]);
  }, [file]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const close = (e) => menu.current && !menu.current.contains(e.target) && setOpen(false);
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);

  const records = useMemo(() => (file ? Object.fromEntries(file.chart.records.map((r) => [r.id, r])) : {}), [file]);

  function run(text) {
    if (!file || !text.trim()) return;
    const t0 = performance.now();
    const a = engine.ask(file.chart, text);
    setMs(performance.now() - t0);
    setAnswer(a);
    setAsked(text.trim());
    setQ("");
    setExpanded(null);
  }

  // every cited record, numbered once in order of first appearance; long series collapse into one row
  const sources = useMemo(() => {
    const out = [];
    const seen = new Set();
    for (const c of answer?.claims || []) {
      if (c.cites.length > 8) continue;
      for (const id of c.cites) if (!seen.has(id)) {
        seen.add(id);
        out.push(id);
      }
    }
    return out;
  }, [answer]);
  const num = (id) => sources.indexOf(id) + 1;

  return (
    <section className="pad" aria-label="Ask a question">
      <div className="who" ref={menu}>
        <button className="who-btn" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span className="avatar">{patient.name[0]}</span>
          <span className="who-text">
            <span className="who-name">{patient.name}</span>
            <span className="mono dim">
              {patient.sex === "female" ? "F" : "M"} · {yearsBetween(patient.birthDate, meta.asOf)} · {patient.records.toLocaleString()} RECORDS
            </span>
          </span>
          <Chevron down />
        </button>
        {open && (
          <ul className="menu" role="listbox">
            {meta.patients.map((p) => (
              <li key={p.id}>
                <button role="option" aria-selected={p.id === pid} className={p.id === pid ? "on" : ""}
                  onClick={() => {
                    setPid(p.id);
                    setOpen(false);
                  }}>
                  <span>{p.name}</span>
                  <span className="mono dim">
                    {p.sex === "female" ? "F" : "M"} · {yearsBetween(p.birthDate, meta.asOf)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form className="field" onSubmit={(e) => {
        e.preventDefault();
        run(q);
      }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about this patient" aria-label="Question" disabled={!file} />
        <button type="submit" className="btn" disabled={!file || !q.trim()}>
          Ask
        </button>
      </form>

      <div className="try">
        {patient.suggest.map((s) => (
          <button key={s} onClick={() => run(s)} disabled={!file}>
            {s}
          </button>
        ))}
      </div>

      {answer && (
        <div className="answer" aria-live="polite">
          <p className="label">{asked}</p>
          <p className="said">
            {answer.claims.map((c, i) => (
              <span key={i}>
                {c.text}
                {c.cites.length > 0 && c.cites.length <= 8 && <sup>{[...new Set(c.cites.map(num))].map((n) => (
                  <button key={n} className={`cite ${expanded === sources[n - 1] ? "on" : ""}`}
                    onClick={() => setExpanded(expanded === sources[n - 1] ? null : sources[n - 1])}>{n}</button>
                ))}</sup>}{" "}
              </span>
            ))}
          </p>
          <p className="mono dim meta">
            <span className={`st st-${answer.status}`}>{STATUS[answer.status].toUpperCase()}</span>
            {sources.length > 0 && ` · ${sources.length} SOURCE${sources.length === 1 ? "" : "S"} · NUMBERS AND DATES CHECKED`}
            {` · ${ms < 1 ? "<1" : Math.round(ms)} MS`}
          </p>

          {sources.length > 0 && (
            <div className="group">
              <p className="label">Sources</p>
              <ul className="rows">
                {sources.map((id, i) => (
                  <Source key={id} n={i + 1} id={id} rec={records[id]} raw={file?.raw?.[id]} chart={file.chart}
                    open={expanded === id} onToggle={() => setExpanded(expanded === id ? null : id)} />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Source({ n, id, rec, raw, chart, open, onToggle }) {
  const isPatient = id === chart.id;
  const name = isPatient ? chart.name : rec?.name;
  const kind = isPatient ? "Patient" : TYPE[rec?.type] || "Record";
  const date = isPatient ? chart.birthDate : rec?.date;
  return (
    <li className={`src ${open ? "open" : ""}`}>
      <button className="row" onClick={onToggle} aria-expanded={open}>
        <span className="mono n">{n}</span>
        <span className="row-main">
          <span className="row-title">{name}</span>
          <span className="row-sub">{kind}{rec?.code ? ` · ${rec.system.toUpperCase()} ${rec.code}` : ""}</span>
        </span>
        <span className="mono dim">{date ? fmtDate(date).toUpperCase() : ""}</span>
        <Chevron down={open} />
      </button>
      {open && <pre className="json">{isPatient ? JSON.stringify({ resourceType: "Patient", id, birthDate: chart.birthDate, gender: chart.sex }, null, 2)
        : raw ? JSON.stringify(raw, null, 2) : "Not included in this demo."}</pre>}
    </li>
  );
}

/* ---- results ---------------------------------------------------------------------------- */

function Results({ r, meta }) {
  const H = (name) => r[name].by_split.heldout;
  const rows = r.categories.filter(([k]) => r.rounds.by_category[k]);
  return (
    <section className="pad">
      <p className="big mono">{pct1(H("rounds").correct, H("rounds").n)}</p>
      <p className="label">Correct · held-out wording · {H("rounds").n.toLocaleString()} questions</p>
      <p className="line">
        <span className="mono">{pct1(H("rag20").correct, H("rag20").n)}</span> search, top 20 · <span className="mono">{pct1(H("rag5").correct, H("rag5").n)}</span> search, top 5
      </p>

      <div className="group">
        <p className="label">Confident wrong answers</p>
        <ul className="rows">
          <Row label="Rounds" value={H("rounds").wrong_answers} />
          <Row label="Search, top 20 records" value={H("rag20").wrong_answers} />
          <Row label="Search, top 5 records" value={H("rag5").wrong_answers} />
        </ul>
      </div>

      <div className="group">
        <div className="label cols">
          <span>By question type</span>
          <span className="mono">ROUNDS</span>
          <span className="mono">TOP 20</span>
          <span className="mono">TOP 5</span>
        </div>
        <ul className="rows">
          {rows.map(([k, label]) => {
            const v = ["rounds", "rag20", "rag5"].map((n) => r[n].by_category[k].heldout);
            return (
              <li key={k} className="row cols">
                <span className="row-title">{label}</span>
                {v.map((x, i) => (
                  <span key={i} className={`mono ${i ? "dim" : ""} ${i && x < 0.5 ? "low" : ""}`}>{whole(x)}</span>
                ))}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="group notes">
        <p className="label">Method</p>
        <p>
          {r.questions.toLocaleString()} questions about {meta.cohort} synthetic patients. Each has an answer key computed from the record by separate code,
          and is asked in wording written by someone who never saw the parser.
        </p>
        <p>
          Search is the usual approach: retrieve the records most similar to the question and answer from those. It uses the same vocabulary and answer
          logic as Rounds, so the only difference is what it reads.
        </p>
        <p>
          With the wording it was built on, Rounds scores {pct1(r.rounds.by_split.dev.correct, r.rounds.by_split.dev.n)}. The first held-out run scored{" "}
          {pct1(r.first_run_heldout.correct, r.first_run_heldout.n)}; it exposed one vocabulary bug, and fixing only that gives{" "}
          {pct1(H("rounds").correct, H("rounds").n)}.
        </p>
      </div>
    </section>
  );
}

function Row({ label, value }) {
  return (
    <li className="row">
      <span className="row-title">{label}</span>
      <span className="mono dim">{value.toLocaleString()}</span>
    </li>
  );
}

/* ---- how --------------------------------------------------------------------------------- */

function How() {
  const groups = [
    ["Data", [
      ["FHIR R4 records", "Synthetic patients from Synthea, pinned version and seeds. Labs, vitals, conditions, medication orders, allergies, vaccines and visits, each with its resource id."],
    ]],
    ["Question", [
      ["Vocabulary", "How clinicians say it, mapped to codes: “A1c” to LOINC, “high blood pressure” to SNOMED, “a statin” to every statin order in RxNorm."],
      ["Parser", "Finds the terms, the time frame and what is asked. No model. Anything it cannot place is refused, not guessed."],
    ]],
    ["Answer", [
      ["Whole-chart query", "Latest means newest by time, current means an active order. The answer is computed over every record, not a retrieved few."],
      ["Citations", "Each sentence carries the ids of the records it rests on."],
      ["Checker", "Every number and date must appear in the cited records. It works on any answerer, including a language model."],
    ]],
  ];
  return (
    <section className="pad">
      {groups.map(([label, items]) => (
        <div className="group" key={label}>
          <p className="label">{label}</p>
          <ul className="rows">
            {items.map(([t, d]) => (
              <li key={t} className="row stack">
                <span className="row-title">{t}</span>
                <span className="row-sub">{d}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="group">
        <p className="label">Limits</p>
        <ul className="rows">
          <li className="row stack">
            <span className="row-sub">Synthetic data, structured fields only, no clinical notes. Not for clinical use.</span>
          </li>
        </ul>
      </div>
    </section>
  );
}

/* ---- icons ------------------------------------------------------------------------------- */

const Chevron = ({ down }) => (
  <svg className={`chev ${down ? "down" : ""}`} width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const Moon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M13 9.6A5.5 5.5 0 0 1 6.4 3a5.5 5.5 0 1 0 6.6 6.6Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
  </svg>
);
const Sun = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="2.8" fill="none" stroke="currentColor" strokeWidth="1.4" />
    <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);
