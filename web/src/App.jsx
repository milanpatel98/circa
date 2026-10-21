import { useEffect, useMemo, useRef, useState } from "react";
import { Engine, fmtDate, yearsBetween } from "./circa.js";

const NAME = "Circa";
const REPO = "https://github.com/milanpatel98/circa";

const KIND = { Observation: "Lab or vital", Condition: "Condition", MedicationRequest: "Medication", AllergyIntolerance: "Allergy",
  Immunization: "Vaccine", Encounter: "Visit", Procedure: "Procedure" };
const STATUS = { answered: "Answered", not_found: "Not in record", unsupported: "Outside record", advice: "Declined" };
const LISTS = new Set(["med_list", "problem_list", "allergy_list", "vaccine_list"]);
const is = (...types) => (r) => types.includes(r.type);
const LANES = [["Visits", is("Encounter")], ["Labs", is("Observation")], ["Conditions", is("Condition")], ["Medications", is("MedicationRequest")],
  ["Vaccines", is("Immunization")]];
const MED_TYPES = ["MedicationRequest", "MedicationAdministration", "MedicationDispense", "MedicationStatement"];
const HOSPITAL_LANES = [["Visits", is("Encounter")], ["Labs", (r) => r.type === "Observation" && (r.cat === "lab" || r.cat === "micro")],
  ["Vitals, ICU", (r) => r.type === "Observation" && r.cat !== "lab" && r.cat !== "micro"], ["Diagnoses", is("Condition")],
  ["Medications", is(...MED_TYPES)], ["Procedures", is("Procedure")]];

// a hospital chart can hold 50,000 records; draw one mark per pixel column per lane, keeping cited records findable
function laneMarks(records, lanes, from, x) {
  const out = [], seen = new Set();
  lanes.forEach(([, match], i) => {
    for (const r of records) {
      if (r.date < from || !match(r)) continue;
      const key = `${i}:${Math.round(x(r.date))}:${r.type === "Condition" ? (r.end || "") : ""}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ r, i });
    }
  });
  return out;
}
const YEARS = 12;
const pct = (k, n) => `${(Math.round((k / n) * 1000) / 10).toFixed(1)}%`;
const brand = (s) => s.replace(/\bCirca\b/g, NAME);
const initials = (name) => (/^Patient \d+$/.test(name) ? `#${name.slice(-3)}` : name.split(" ").map((w) => w[0]).join(""));
const pron = (sex) => (sex === "female" ? ["her", "she"] : ["his", "he"]);

const CATS = [
  ["Labs", [["Last A1c", (p) => `What was ${p} last A1c?`], ["Blood pressure trend", (p) => `How has ${p} blood pressure changed?`],
    ["Latest LDL", (p) => `What was ${p} last LDL?`], ["Weight over time", (p) => `How has ${p} weight changed?`]]],
  ["Medications", [["Current medications", (p, s) => `What medications is ${s} on?`], ["Blood thinner?", (p, s) => `Is ${s} on a blood thinner?`],
    ["Statin?", (p, s) => `Is ${s} on a statin?`], ["Treatment question", (p) => `Should we increase ${p} lisinopril?`]]],
  ["Conditions", [["Problem list", (p) => `What are ${p} active problems?`], ["Diabetes?", (p, s) => `Does ${s} have diabetes?`],
    ["Hypertension?", (p, s) => `Does ${s} have hypertension?`], ["Asthma?", (p, s) => `Does ${s} have asthma?`]]],
  ["Allergies", [["All allergies", () => "Any allergies?"], ["Penicillin?", (p, s) => `Is ${s} allergic to penicillin?`],
    ["Peanuts?", (p, s) => `Is ${s} allergic to peanuts?`]]],
  ["Vaccines", [["Last flu shot", (p) => `When was ${p} last flu shot?`], ["COVID vaccine", (p) => `When was ${p} last covid vaccine?`],
    ["Tetanus", (p) => `When was ${p} last tetanus shot?`]]],
  ["Visits", [["Last visit", (p, s) => `When was ${s} last seen?`], ["ER this year", () => "How many ER visits in the past year?"],
    ["Age", (p, s) => `How old is ${s}?`]]],
];

// hospital records: inpatient labs, orders from the last stay, diagnoses by stay, no allergies or vaccines
const HOSPITAL_CATS = [
  ["Labs", [["Last A1c", (p) => `What was ${p} last A1c?`], ["Creatinine trend", (p) => `How has ${p} creatinine changed?`],
    ["Hemoglobin trend", (p) => `How has ${p} hemoglobin changed?`], ["Last potassium", (p) => `What was ${p} last potassium?`]]],
  ["Medications", [["Current medications", (p, s) => `What medications is ${s} on?`], ["Blood thinner?", (p, s) => `Is ${s} on a blood thinner?`],
    ["Insulin?", (p, s) => `Is ${s} on insulin?`], ["Treatment question", (p) => `Should we increase ${p} insulin?`]]],
  ["Conditions", [["Diagnoses", (p) => `What are ${p} active problems?`], ["Diabetes?", (p, s) => `Does ${s} have diabetes?`],
    ["Heart failure?", (p, s) => `Does ${s} have heart failure?`], ["Kidney disease?", (p, s) => `Does ${s} have kidney disease?`]]],
  CATS[CATS.length - 1],
];

function useNarrow() {
  const q = "(max-width: 700px)";
  const [n, setN] = useState(() => matchMedia(q).matches);
  useEffect(() => {
    const m = matchMedia(q);
    const on = () => setN(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return n;
}

const Icon = ({ d, size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square">
    {d}
  </svg>
);
const I = {
  ask: <><path d="M4 5h16v11H9l-5 4z" /><path d="M8.5 10.5h7" /></>,
  chart: <><path d="M4 20V4" /><path d="M4 20h16" /><path d="M8 16v-5M12 16V8M16 16v-3" /></>,
  home: <><path d="M4 11l8-6 8 6v9H4z" /><path d="M10 20v-5h4v5" /></>,
  people: <><rect x="4" y="4" width="7" height="7" /><rect x="13" y="4" width="7" height="7" /><rect x="4" y="13" width="7" height="7" /><rect x="13" y="13" width="7" height="7" /></>,
  arrow: <path d="M5 12h13M13 6l6 6-6 6" />,
};

function Dock({ page }) {
  const items = [["home", "Home", "#", I.home], ["patients", "Patients", "#/patients", I.people], ["results", "Results", "#/results", I.chart]];
  return (
    <nav className="dock" aria-label="Main">
      {items.map(([k, label, href, icon]) => (
        <a key={k} href={href} className={page === k ? "on" : ""} aria-current={page === k ? "page" : undefined}><Icon d={icon} size={22} /><span>{label}</span></a>
      ))}
    </nav>
  );
}

function useRoute() {
  const read = () => {
    const h = location.hash;
    if (h.startsWith("#/p/")) return { page: "patient", id: h.slice(4) };
    if (h === "#/results") return { page: "results" };
    if (h === "#/patients" || h === "#patients") return { page: "patients" };
    return { page: "home", anchor: h.slice(1) };
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => setRoute(read());
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    if (route.page === "home" && route.anchor) document.getElementById(route.anchor)?.scrollIntoView();
    else scrollTo(0, 0);
  }, [route]);
  return route;
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [lex, setLex] = useState(null);
  const [results, setResults] = useState(null);
  const route = useRoute();

  useEffect(() => {
    Promise.all(["patients", "lexicon", "results"].map((f) => fetch(`data/${f}.json?v=${__BUILD__}`).then((r) => r.json()))).then(([p, l, r]) => {
      setMeta(p);
      setLex(l);
      setResults(r);
    });
  }, []);
  const engine = useMemo(() => (lex ? new Engine(lex) : null), [lex]);
  if (!meta || !engine || !results) return <div className="boot" />;

  const patient = route.page === "patient" ? meta.patients.find((p) => p.id === route.id) : null;
  return (
    <>
      {route.page === "home" && <Home meta={meta} />}
      {route.page === "patients" && <Patients meta={meta} />}
      {route.page === "patient" && patient && <Patient key={patient.id} meta={meta} patient={patient} engine={engine} />}
      {route.page === "results" && <Results r={results} />}
      <Dock page={route.page === "results" ? "results" : route.page === "home" ? "home" : "patients"} />
      <footer className={`foot wrap ${route.page === "home" ? "on-home" : ""}`}>
        <span>© 2026 Milan Patel · MIT License</span>
        <a href={REPO}>GitHub</a>
      </footer>
    </>
  );
}

function Nav({ dark }) {
  return (
    <header className={`nav wrap ${dark ? "on-olive" : ""}`}>
      <a href="#" className="logo"><Logo />{NAME}</a>
      <nav>
        <a href="#/patients">Patients</a>
        <a href="#/results">Results</a>
      </nav>
    </header>
  );
}

// the mark: a square C holding one square, the chart around the one record that backs the answer
const Logo = () => (
  <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true">
    <path d="M26 7.5H6.5V24.5H26" fill="none" stroke="currentColor" strokeWidth="4.2" />
    <rect x="13" y="13" width="6" height="6" fill="currentColor" />
  </svg>
);

/* ---- the record drawn as a timeline ------------------------------------------------------- */

function Timeline({ chart, asOf, cited = [], tone = "light", labels = true, callout }) {
  const compact = useNarrow();
  const lanes = chart.source === "hospital" ? HOSPITAL_LANES : LANES;
  // fit the window to the record: from the first record (a little before) to "today", at most 6 or 12 years
  const firstAt = useMemo(() => chart.records.reduce((m, r) => (r.date < m ? r.date : m), asOf), [chart, asOf]);
  const spanYears = (Date.parse(asOf) - Date.parse(firstAt)) / (365.25 * 864e5);
  const YEARS = Math.min(compact ? 6 : 12, Math.max(1, Math.ceil(spanYears * 1.08 + 0.15)));
  const W = compact ? 560 : 1000, lane = compact ? 44 : 30, top = callout ? (compact ? 84 : 64) : 10, left = labels ? (compact ? 150 : 112) : 0;
  const H = top + lanes.length * lane + 34;
  const end = Date.parse(asOf), start = end - YEARS * 365.25 * 864e5;
  const x = (d) => left + ((Date.parse(d) - start) / (end - start)) * (W - left - 8);
  const citedSet = new Set(cited);
  const from = new Date(start).toISOString().slice(0, 10);
  const marks = useMemo(() => laneMarks(chart.records, lanes, from, x), [chart, lanes, compact]); // eslint-disable-line react-hooks/exhaustive-deps
  const hits = useMemo(() => {
    const out = [];
    lanes.forEach(([, match], i) => chart.records.forEach((r) => citedSet.has(r.id) && r.date >= from && match(r) && out.push({ r, i })));
    return out;
  }, [chart, lanes, cited]); // eslint-disable-line react-hooks/exhaustive-deps
  const y0 = new Date(start).getUTCFullYear() + 1;
  const first = hits[0];
  return (
    <svg className={`tl ${tone} ${compact ? "compact" : ""}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${chart.name}'s record over ${YEARS} years`}>
      {lanes.map(([name], i) => (
        <g key={name}>
          <line x1={left} x2={W - 8} y1={top + i * lane + lane / 2} y2={top + i * lane + lane / 2} className="tl-rule" />
          {labels && <text x={0} y={top + i * lane + lane / 2 + 4} className="tl-lane">{name}</text>}
        </g>
      ))}
      {marks.map(({ r, i }) =>
        r.type === "Condition" ? (
          <rect key={r.id} x={x(r.date)} y={top + i * lane + lane / 2 - 2} width={Math.max(3, x(r.end || asOf) - x(r.date))} height={4} className="tl-span" />
        ) : (
          <rect key={r.id} x={x(r.date) - 1} y={top + i * lane + 8} width={2} height={lane - 16} className="tl-mark" />
        ))}
      {hits.map(({ r, i }) => (
        <rect key={`h${r.id}`} x={x(r.date) - 4} y={top + i * lane + 5} width={8} height={lane - 10} className="tl-hit" />
      ))}
      {callout && first && (
        <g className="tl-call">
          <line x1={x(first.r.date)} x2={x(first.r.date)} y1={top - 18} y2={top + first.i * lane + 5} />
          <foreignObject x={compact ? 0 : Math.min(x(first.r.date) - 300, W - 430)} y={0} width={compact ? W : 420} height={compact ? 70 : 46}>
            <div className="callout">{callout}</div>
          </foreignObject>
        </g>
      )}
      {Array.from({ length: YEARS + 1 }, (_, k) => y0 + k).filter((y) => (y - y0) % (YEARS > (compact ? 3 : 6) ? 2 : 1) === 0 && Date.parse(`${y}-01-01`) < end).map((y) => (
        <text key={y} x={x(`${y}-01-01`)} y={H - 8} className="tl-year">{y}</text>
      ))}
    </svg>
  );
}

// patient files are stored gzipped; the browser unpacks them unless the server already did
async function loadPatient(id, folder = "p") {
  const buf = new Uint8Array(await (await fetch(`data/${folder}/${id}.json.gz?v=${__BUILD__}`)).arrayBuffer());
  if (buf[0] !== 0x1f || buf[1] !== 0x8b) return JSON.parse(new TextDecoder().decode(buf));
  const text = await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"))).text();
  return JSON.parse(text);
}

function Spark({ counts }) {
  const max = Math.max(...counts);
  return (
    <svg className="spark" viewBox="0 0 120 28" preserveAspectRatio="xMinYMid meet" aria-hidden="true">
      {counts.map((c, i) => (
        <rect key={i} x={i * 10 + 1} y={28 - Math.max(2, (c / max) * 26)} width={7} height={Math.max(2, (c / max) * 26)} />
      ))}
    </svg>
  );
}

/* ---- home ------------------------------------------------------------------------------------ */

function Home({ meta }) {
  return (
    <section className="home">
      <Nav dark />
      <div className="home-center">
        <Drawing />
        <h1>Ask the chart. Get the proof.</h1>
        <a className="btn light big home-btn" href="#/patients"><Icon d={I.ask} />Ask a patient</a>
        <p className="home-note">{meta.patients.length} real hospital patients ready</p>
      </div>
    </section>
  );
}

/* one drawn idea: a record over time, one mark picked out, and the answer it backs */
function Drawing() {
  const rows = [
    [18, 46, 70, 96, 130, 158, 190],
    [30, 60, 84, 120, 150, 176, 206],
    [24, 52, 104, 140, 168, 198],
  ];
  return (
    <svg className="drawing" viewBox="0 0 260 150" aria-hidden="true">
      <rect x="1" y="1" width="258" height="148" className="dr-frame" />
      {rows.map((xs, i) => (
        <g key={i}>
          <line x1="16" x2="244" y1={44 + i * 30} y2={44 + i * 30} className="dr-rule" />
          {xs.map((x) => <rect key={x} x={x} y={36 + i * 30} width="2.5" height="16" className="dr-mark" />)}
        </g>
      ))}
      <rect x="221" y="62" width="9" height="24" className="dr-hit" />
      <line x1="225.5" x2="225.5" y1="62" y2="30" className="dr-lead" />
      <rect x="150" y="12" width="94" height="18" className="dr-tag" />
      <rect x="157" y="19" width="50" height="4" className="dr-tag-ink" />
      <rect x="212" y="19" width="24" height="4" className="dr-tag-ink" />
    </svg>
  );
}

function PatientCard({ p }) {
  return (
    <a className="card" href={`#/p/${p.id}`}>
      <span className="mono">{initials(p.name)}</span>
      <span className="card-name">{p.name}</span>
      <span className="soft">{yearsBetween(p.birthDate, p.asOf)}, {p.sex}</span>
      <Spark counts={p.spark} />
      <span className="card-stats">
        <span><b>{p.stays}</b> {p.stays === 1 ? "hospital stay" : "hospital stays"}</span>
        <span><b>{p.meds}</b> recent medications</span>
      </span>
      <span className="card-go">Open chart <Icon d={I.arrow} size={16} /></span>
    </a>
  );
}

function Patients({ meta }) {
  const [find, setFind] = useState("");
  const term = find.trim().toLowerCase();
  const hits = term ? meta.patients.filter((p) => p.name.toLowerCase().includes(term) || p.sex === term) : null;
  const shown = hits || meta.patients;
  return (
    <>
      <section className="hero slim">
        <Nav dark />
        <div className="wrap">
          <h1 className="page-title">Choose a patient</h1>
        </div>
      </section>
      <section className="wrap block tight">
        <div className="find">
          <input value={find} onChange={(e) => setFind(e.target.value)} placeholder={`Search ${meta.patients.length} patients by number`} aria-label="Search patients" inputMode="numeric" />
        </div>
        {hits && !hits.length && <p className="soft">No patient number matches “{find}”.</p>}
        <div className="cards">
          {shown.map((p) => <PatientCard key={p.id} p={p} />)}
        </div>
        <p className="credit">
          Real, de-identified patients from the <a href="https://physionet.org/content/mimic-iv-fhir-demo/2.1.0/">MIMIC-IV Clinical Database Demo on FHIR</a> on PhysioNet, Open Database License.
        </p>
      </section>
    </>
  );
}

/* ---- a patient ------------------------------------------------------------------------------- */

function Patient({ meta, patient, engine }) {
  const [file, setFile] = useState(null);
  const [raw, setRaw] = useState(null);
  const [cat, setCat] = useState("Labs");
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState(null);
  const [asked, setAsked] = useState("");
  const [sheet, setSheet] = useState(null);
  const [poss, subj] = pron(patient.sex);
  const cats = file?.chart.source === "hospital" ? HOSPITAL_CATS : CATS;
  const first = patient.name.split(" ")[0];

  useEffect(() => {
    setFile(null);
    setRaw(null);
    loadPatient(patient.id).then(setFile);
  }, [patient.id]);
  useEffect(() => {
    if (sheet && !raw) loadPatient(patient.id, "r").then(setRaw);
  }, [sheet, raw, patient.id]);
  useEffect(() => {
    const esc = (e) => e.key === "Escape" && setSheet(null);
    addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, []);

  const records = useMemo(() => (file ? Object.fromEntries(file.chart.records.map((r) => [r.id, r])) : {}), [file]);
  useEffect(() => {
    if (answer && matchMedia("(max-width: 700px)").matches) document.querySelector(".said")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [answer]);
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
    return n ? <button className={`cite ${sheet === id ? "on" : ""}`} onClick={() => setSheet(id)} aria-label={`Record ${n}`}>{n}</button> : null;
  };

  return (
    <>
      <section className="hero slim">
        <Nav dark />
        <div className="wrap">
          <div className="pt-head">
            <span className="mono big-mono">{initials(patient.name)}</span>
            <div>
              <h1 className="pt-name">{patient.name}</h1>
              <p className="pt-sub">{yearsBetween(patient.birthDate, patient.asOf)}, {patient.sex}. {patient.records.toLocaleString()} real hospital records, dates shifted for privacy.</p>
            </div>
            <select className="switch" value={patient.id} onChange={(e) => (location.hash = `#/p/${e.target.value}`)} aria-label="Switch patient">
              {meta.patients.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <figure className="hero-fig flat">
            {file ? <Timeline chart={file.chart} asOf={patient.asOf} cited={sources} tone="dark" /> : <div className="tl-wait" />}
          </figure>
        </div>
      </section>

      <section className="wrap ask">
        <div className="tabs" role="tablist" aria-label="Category">
          {cats.map(([k]) => (
            <button key={k} role="tab" aria-selected={cat === k} className={cat === k ? "on" : ""} onClick={() => setCat(k)}>{k}</button>
          ))}
        </div>
        <div className="qs">
          {(cats.find(([k]) => k === cat) || cats[0])[1].map(([label, make]) => (
            <button key={label} className="btn chip" onClick={() => run(make(poss, subj))} disabled={!file}>{label}</button>
          ))}
        </div>
        <form className="field" onSubmit={(e) => { e.preventDefault(); run(q); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Or type a question" aria-label="Question" disabled={!file} />
          <button type="submit" className="btn dark" disabled={!file || !q.trim()}>Ask</button>
        </form>

        {answer && (
          <article className="said" aria-live="polite">
            <div className="said-head">
              <p className="soft">{asked}</p>
              <span className={`tag ${answer.status}`}>{STATUS[answer.status]}</span>
            </div>
            {isList ? (
              <>
                <p className="said-text">{answer.claims[0].text.replace(/:$/, ".")}</p>
                <ul className="rows">
                  {answer.claims.slice(1).map((c, i) => (
                    <li key={i}><span>{c.text.replace(/[;.]$/, "")}</span><Mark id={c.cites[0]} /></li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="said-text">
                {answer.claims.map((c, i) => (
                  <span key={i}>{brand(c.text)}{c.cites.length > 0 && c.cites.length <= 8 && c.cites.map((id) => <Mark key={id} id={id} />)}{" "}</span>
                ))}
              </p>
            )}
            {sources.length > 0 && (
              <p className="said-foot">
                <span className="dot" /> Highlighted on the timeline above.
                <button className="btn line-dark" onClick={() => setSheet("all")}>View {sources.length === 1 ? "record" : `${sources.length} records`}</button>
              </p>
            )}
          </article>
        )}
      </section>

      {sheet && file && <Sheet ids={sources} focus={sheet === "all" ? null : sheet} records={records} raw={raw} chart={file.chart} onClose={() => setSheet(null)} />}
    </>
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
          <p>Source records</p>
          <button onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" /></svg>
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
                    <span className="soft">{isPatient ? `Patient, born ${fmtDate(chart.birthDate)}` : `${KIND[r?.type] || "Record"}, ${fmtDate(r.date)}`}</span>
                  </span>
                </button>
                {isOpen && (
                  <pre className="fhir">
                    {isPatient ? JSON.stringify({ resourceType: "Patient", id, gender: chart.sex, birthDate: chart.birthDate }, null, 2)
                      : !raw ? "Loading the original record…" : raw[id] ? JSON.stringify(raw[id], null, 2) : "Not in the source release."}
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

/* ---- results ---------------------------------------------------------------------------------- */

function Results({ r }) {
  const [set, setSet] = useState("real");
  const [more, setMore] = useState(false);
  const d = r[set];
  const H = (n) => d[n].by_split.heldout;
  const all = r.categories.map(([k]) => k).filter((k) => d.circa.by_category[k]);
  const keys = more ? all : ["latest", "trend", "med_active", "meds", "problems", "last_visit"].filter((k) => all.includes(k));
  const label = Object.fromEntries(r.categories);
  return (
    <>
      <section className="hero slim">
        <Nav dark />
        <div className="wrap res-head">
          <div className="seg-sq" role="tablist" aria-label="Patients">
            {[["real", "Real patients"], ["synthetic", "Synthetic patients"]].map(([k, l]) => (
              <button key={k} role="tab" aria-selected={set === k} className={set === k ? "on" : ""} onClick={() => setSet(k)}>{l}</button>
            ))}
          </div>
          <p className="res-big">{pct(H("circa").correct, H("circa").n)}</p>
          <p>
            correct on {H("circa").n.toLocaleString()} questions worded by someone who never saw how {NAME} reads them.{" "}
            {set === "real" ? "100 real hospital patients from MIMIC-IV." : "130 Synthea patients."}
          </p>
        </div>
      </section>
      <section className="wrap block">
        <div className="block-head">
          <h2>Against the usual approach</h2>
          <p>Search answers from the records that read most like the question. {NAME} reads the whole chart.</p>
        </div>
        <div className="mini-bars wide">
          {[[NAME, "circa"], ["Search, top 20", "rag20"], ["Search, top 5", "rag5"]].map(([name, k]) => (
            <div key={k} className={`mb ${k === "circa" ? "ours" : ""}`}>
              <span>{name}</span>
              <span className="mb-track"><span style={{ width: `${(H(k).correct / H(k).n) * 100}%` }} /></span>
              <span>{pct(H(k).correct, H(k).n)}</span>
            </div>
          ))}
        </div>
        <div className="wrongs">
          {[[NAME, "circa"], ["Search, top 20", "rag20"], ["Search, top 5", "rag5"]].map(([name, k]) => (
            <div key={k} className={k === "circa" ? "ours" : ""}>
              <b>{H(k).wrong_answers}</b>
              <span>confident wrong answers, {name}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="wrap block">
        <div className="block-head"><h2>By question</h2></div>
        <table className="t">
          <thead><tr><th scope="col">Question</th><th scope="col">{NAME}</th><th scope="col">Search, 20</th></tr></thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k}>
                <td>{label[k]}</td>
                <td><b>{Math.round(d.circa.by_category[k].heldout * 100)}%</b></td>
                <td className="soft">{Math.round(d.rag20.by_category[k].heldout * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="btn line-dark" onClick={() => setMore((m) => !m)} aria-expanded={more}>{more ? "Show fewer" : `Show all ${all.length}`}</button>
        <p className="credit">
          Real patients: <a href="https://physionet.org/content/mimic-iv-fhir-demo/2.1.0/">MIMIC-IV Clinical Database Demo on FHIR</a> on PhysioNet, Open Database License.
        </p>
      </section>
    </>
  );
}
