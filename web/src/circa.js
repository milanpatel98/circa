// A line-by-line port of circa/lexicon.py (norm), parse.py and engine.py.
// test/parity.mjs asks every benchmark question for the demo patients and checks the answers match Python exactly.

export function norm(text) {
  const t = text.toLowerCase().replaceAll("’", "").replaceAll("'", "");
  return t.replace(/[^a-z0-9]+/g, " ").trim().split(/\s+/).filter(Boolean).join(" ");
}

const STOP = new Set(`a an the of to in on for and or with is are was were be been being do does did has have had he she they him her them
his their its it this that these those what whats which who whom when where why how any all some me my i you your we our us
please tell show give list get find check pt patient patients s ever still now currently current today recent recently latest last most
there here from by at as about since before after during over past than then up down out into not no yes ok if so can could would will
should may might must also just only much many more less again`.split(/\s+/));

const CUES = {
  advice: /\b(should|recommend\w*|advis\w*|ok to|okay to|safe to|safe for|alright to|can (i|we|you|he|she|they) (give|take|start|stop|use|add|restart|resume)|what dose|which dose|what should|how much \w+ should|increase|decrease|titrate|discontinue|switch|prescribe|dosing|uptitrate|wean|taper|worth starting|need to start|needs? (a|an|to)|what would you|what do you think|is it time to|would you)\b/,
  age: /\b(how old|age|years old|date of birth|dob|birthday|born)\b/,
  allergy: /\b(allerg\w*|reactions?|intoleran\w*|nkda|anaphyla\w*)\b/,
  vaccine: /\b(vaccin\w*|shots?|jabs?|immuni[sz]\w*|boosters?|inoculat\w*|doses?)\b/,
  er: /\b(er|ed|emergency|emerg|a e|e r|casualty)\b/,
  outside: /\b(family|mother|father|mom|dad|siblings?|brothers?|sisters?|parents?|grand\w*|relatives?|mri|x ray|xray|ct|cat scan|ultrasound|echo\w*|imaging|scans?|biops\w*|genetic\w*|genes?|dna|insurance|insurer|coverage|copay|doctor|physician|provider|pcp|specialist|nurse|diet|eat\w*|exercis\w*|workouts?|sleep\w*|said|say|says|complain\w*|feel\w*|mood|job|occupation|work|address|phone|email|married|lives?|pharmacy|cost|price)\b/,
  admit: /\b(hospitali[sz]\w*|admitted|admissions?|admits?|inpatient|hospital stays?)\b/,
  visit: /\b(visits?|seen|appointments?|appts?|encounters?|came in|come in|office|check ?ups?|clinic)\b|\blast\b.*\b(see|saw)\b|\b(see|saw)\b.*\blast\b/,
  med: /\b(meds?|medications?|medicines?|prescri\w*|drugs?|pills?|rx|taking|takes|take|on any|regimen|scripts?)\b|\b(still|currently|now) on\b|\b(is|are|was|were) (he|she|they|the patient|pt|patient) (currently |still |now )?on\b/,
  start: /\b(start\w*|begin|began|begun|first|initiat\w*|put on|commenced|since when|how long)\b/,
  problem: /\b(problems?|diagnos[ie]s|dx|dxs|conditions?|medical history|pmh|hx|history|issues|comorbidit\w*|illness\w*|diseases?|ailments?|wrong)\b/,
  has: /\b(have|has|had|diagnos\w*|history of|hx of|hx|dx|dx of|suffer\w*|with|got|gets|known|positive)\b/,
  trend: /\b(trend\w*|over time|chang\w*|history|series|serial|track\w*|going up|going down|gone up|gone down|go up|go down|went up|went down|increased|decreased|increasing|decreasing|improv\w*|wors\w*|rising|rise|risen|falling|fallen|up or down|trajector\w*|progress\w*|graph|plot|how (has|have)|been doing|been like|been trending|over the|past few|last few|(last|past|previous|prior) (\d+|few|several|two|three|four|five|six)|over the years|across)\b/,
  trend_weak: /\b(values|readings|results|levels|numbers|all|every|each)\b/,
  latest: /\b(latest|last|most recent|recent|current|currently|newest|now|today|lately)\b/,
};

const NUMWORDS = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, twelve: 12, a: 1 };

const CUE_WORDS = new Set(["medications", "medication", "medicines", "allergies", "allergic", "allergy", "vaccines", "vaccine", "vaccinated", "vaccination",
  "prescribed", "prescription", "emergency", "hospitalized", "appointment", "diagnosed", "diagnosis", "diagnoses", "history",
  "immunizations", "immunization", "received", "latest", "recent", "recently", "currently", "problems", "conditions", "trending",
  "visited", "readings", "results", "started", "starting", "taking", "booster", "admitted", "reactions"]);

const COMMON = new Set(`doing being going think about could would there their where which while those these today right still since
after before other again under every never always value values level levels taken takes times thing things things lately
early later later wants given given given years months weeks hours check checked ready shown known start state stated
house cases cause seems looks looked tests total`.split(/\s+/));

export function osaDistance(a, b, limit = 2) {
  if (Math.abs(a.length - b.length) >= limit) return limit;
  let prev2 = null;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i, ...new Array(b.length).fill(0)];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) cur[j] = Math.min(cur[j], prev2[j - 2] + 1);
    }
    prev2 = prev;
    prev = cur;
  }
  return prev[prev.length - 1];
}

export function minusMonths(iso, months) {
  const y = +iso.slice(0, 4), m = +iso.slice(5, 7), d = +iso.slice(8, 10);
  const total = y * 12 + (m - 1) - months;
  const y2 = Math.floor(total / 12);
  const m2 = total - y2 * 12 + 1;
  const leap = y2 % 4 === 0 && (y2 % 100 !== 0 || y2 % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m2 - 1];
  return `${String(y2).padStart(4, "0")}-${String(m2).padStart(2, "0")}-${String(Math.min(d, days)).padStart(2, "0")}`;
}

function minusDays(iso, days) {
  const t = Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) - days * 86400000;
  return new Date(t).toISOString().slice(0, 10);
}

const isDigits = (s) => /^\d+$/.test(s);
const byKey = (key) => (a, b) => {
  const x = key(a), y = key(b);
  for (let i = 0; i < x.length; i++) {
    if (x[i] < y[i]) return -1;
    if (x[i] > y[i]) return 1;
  }
  return 0;
};

export class Parser {
  constructor(lexicon) {
    this.concepts = Object.fromEntries(lexicon.concepts.map((c) => [c.key, c]));
    this.phrases = new Map();
    for (const c of lexicon.concepts) for (const p of c.phrases) {
      if (!this.phrases.has(p)) this.phrases.set(p, []);
      this.phrases.get(p).push(c.key);
    }
    this.byFirst = new Map();
    const sorted = [...this.phrases.keys()].sort(byKey((p) => [-p.split(" ").length, -p.length, p]));
    for (const p of sorted) {
      const toks = p.split(" ");
      if (!this.byFirst.has(toks[0])) this.byFirst.set(toks[0], []);
      this.byFirst.get(toks[0]).push(toks);
    }
    this.vocab = new Set([...[...this.phrases.keys()].flatMap((p) => p.split(" ")), ...CUE_WORDS]);
    this.fuzzyPool = [...this.vocab].filter((t) => t.length >= 5).sort();
    this.cache = new Map();
  }

  canon(tok) {
    if (this.cache.has(tok)) return this.cache.get(tok);
    let out = tok;
    if (!this.vocab.has(tok) && !STOP.has(tok) && !COMMON.has(tok) && !isDigits(tok)) {
      if (tok.endsWith("es") && this.vocab.has(tok.slice(0, -2))) out = tok.slice(0, -2);
      else if (tok.endsWith("s") && this.vocab.has(tok.slice(0, -1))) out = tok.slice(0, -1);
      else if (tok.length >= 5) {
        let best = null, bestD = 2;
        for (const v of this.fuzzyPool) {
          if (Math.abs(v.length - tok.length) > 1 || (v[0] !== tok[0] && v.slice(1, 2) !== tok.slice(1, 2))) continue;
          const d = osaDistance(tok, v);
          if (d < bestD || (d === bestD && best !== null && v < best)) { best = v; bestD = d; }
        }
        if (best !== null && bestD === 1) out = best;
      }
    }
    this.cache.set(tok, out);
    return out;
  }

  mentions(toks) {
    const out = [];
    let i = 0;
    while (i < toks.length) {
      let hit = null;
      for (const cand of this.byFirst.get(toks[i]) || []) {
        if (cand.every((t, k) => toks[i + k] === t)) { hit = cand; break; }
      }
      if (hit) {
        const phrase = hit.join(" ");
        out.push({ start: i, end: i + hit.length, phrase, keys: this.phrases.get(phrase) });
        i += hit.length;
      } else i += 1;
    }
    return out;
  }

  static window(q, asOf) {
    const y = +asOf.slice(0, 4);
    const m = q.match(/\b(?:in|during|for|from|of)?\s*(?:the\s+)?(?:year\s+)?((?:19|20|21|22)\d\d)\b/);
    const since = q.match(/\b(?:since|after)\s+((?:19|20|21|22)\d\d)\b/);
    if (since) return { start: `${since[1]}-01-01`, end: asOf, label: `since ${since[1]}` };
    const before = q.match(/\bbefore\s+((?:19|20|21|22)\d\d)\b/);
    if (before) return { start: "1900-01-01", end: `${+before[1] - 1}-12-31`, label: `before ${before[1]}` };
    if (m) return { start: `${m[1]}-01-01`, end: `${m[1]}-12-31`, label: `in ${m[1]}` };
    const n = q.match(/\b(?:past|last|previous|prior)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+(months?|years?|yrs?|mos?)\b/);
    if (n) {
      const k = isDigits(n[1]) ? +n[1] : NUMWORDS[n[1]];
      const months = n[2].startsWith("mo") ? k : 12 * k;
      return { start: minusMonths(asOf, months), end: asOf, label: `in the past ${k} ${months === k ? "month" : "year"}${k !== 1 ? "s" : ""}` };
    }
    if (/\b(?:in|over|during|within|for)\s+the\s+(?:past|last|previous|prior)\s+(?:year|12 months|twelve months)\b|\b(?:this past|the past|past) year\b|\b(?:past|last) 12 months\b|\blast twelve months\b/.test(q))
      return { start: minusMonths(asOf, 12), end: asOf, label: "in the past 12 months" };
    if (/\blast year\b/.test(q)) return { start: `${y - 1}-01-01`, end: `${y - 1}-12-31`, label: `in ${y - 1}` };
    if (/\bthis year\b/.test(q)) return { start: `${y}-01-01`, end: asOf, label: `in ${y}` };
    return null;
  }

  parse(question, asOf) {
    const q = norm(question);
    const toks = q ? q.split(" ").map((t) => this.canon(t)) : [];
    const ms = this.mentions(toks);
    const covered = new Set(ms.flatMap((m) => Array.from({ length: m.end - m.start }, (_, k) => m.start + k)));
    const qc = toks.map((t, i) => (covered.has(i) ? "_" : t)).join(" ");
    const cue = Object.fromEntries(Object.entries(CUES).map(([k, re]) => [k, re.test(qc)]));
    const win = Parser.window(q, asOf);
    const C = this.concepts;
    const pick = (kinds) => {
      for (const m of ms) for (const kind of kinds) for (const key of m.keys) if (C[key].kind === kind) return key;
      return null;
    };
    const out = (intent, concept = null, w = win) => ({ intent, concept, window: w, q });
    const past12 = () => ({ start: minusMonths(asOf, 12), end: asOf, label: "in the past 12 months" });

    if (cue.advice) return out("advice", null, null);
    if (cue.age && !ms.length) return out("age", null, null);
    if (cue.allergy) {
      const medAllergyWord = ms.some((m) => m.phrase.includes("allerg"));
      if (!(medAllergyWord && cue.med)) {
        const key = pick(["allergy", "med", "condition", "obs"]);
        return key ? out("allergy_check", key, null) : out("allergy_list", null, null);
      }
    }
    if (cue.outside) return out("unsupported", null, null);
    const vax = pick(["vaccine"]);
    if (vax && (cue.vaccine || !pick(["condition", "med", "obs"]))) return out("vaccine_last", vax, null);
    if (cue.vaccine && !ms.length && !cue.med) return out("vaccine_list", null, null);
    if (cue.er) return out("er_visits", null, win || past12());
    if (cue.admit && !ms.length) return out("admissions", null, win || past12());
    if (cue.visit && !ms.length) return out("last_visit", null, null);

    let first = null;
    for (const m of ms) {
      const kinds = new Set(m.keys.map((k) => C[k].kind).filter((k) => k === "med" || k === "condition" || k === "obs"));
      if (!kinds.size) continue;
      let kind;
      if (kinds.size > 1) {
        const order = cue.med ? ["med", "condition", "obs"] : cue.has ? ["condition", "obs", "med"] : ["obs", "condition", "med"];
        kind = order.find((k) => kinds.has(k));
      } else kind = [...kinds][0];
      first = [kind, m.keys.find((k) => C[k].kind === kind)];
      break;
    }
    if (first && first[0] === "med") return /\bwhen\b/.test(qc) || cue.start ? out("med_start", first[1], null) : out("on_med", first[1], null);
    if (first && first[0] === "condition") return out("has_condition", first[1], null);
    if (first && first[0] === "obs") {
      if (win && /^in \d{4}$/.test(win.label)) return out("latest_value", first[1]);
      if (cue.trend || (cue.trend_weak && !cue.latest)) return out("trend", first[1]);
      return out("latest_value", first[1]);
    }
    if (cue.med) return out("med_list", null, null);
    if (cue.problem) return out("problem_list", null, null);
    if (cue.age) return out("age", null, null);
    return out("unsupported", null, null);
  }
}

// ---- engine -------------------------------------------------------------------------------

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const GENERIC_ALLERGY = /disposition|allergy to substance/i;
const TREND_POINTS = 6;

export const fmtDate = (iso) => `${MONTHS[+iso.slice(5, 7) - 1]} ${+iso.slice(8, 10)}, ${iso.slice(0, 4)}`;

export function fmtNum(v) {
  const s = v.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return s === "-0" ? "0" : s;
}

export function fmtValue(r) {
  if (r.parts) {
    const sys = r.parts.find((p) => p[0] === "8480-6");
    const dia = r.parts.find((p) => p[0] === "8462-4");
    if (sys && dia) return `${fmtNum(sys[2])}/${fmtNum(dia[2])} ${sys[3]}`.trim();
    return r.parts.map((p) => `${p[1]} ${fmtNum(p[2])} ${p[3]}`.trim()).join(", ");
  }
  if ("value" in r) {
    const unit = r.unit || "";
    return unit !== "%" ? `${fmtNum(r.value)} ${unit}`.trim() : `${fmtNum(r.value)}%`;
  }
  return (r.text || "").replace(/\s*\((finding|qualifier value|disorder|organism)\)$/, "");
}

function numeric(r) {
  if (r.parts) {
    const sys = r.parts.find((p) => p[0] === "8480-6");
    return sys ? sys[2] : null;
  }
  return "value" in r ? r.value : null;
}

export function yearsBetween(birth, asOf) {
  let y = +asOf.slice(0, 4) - +birth.slice(0, 4);
  if (asOf.slice(5) < birth.slice(5)) y -= 1;
  return y;
}

const isUpper = (ch) => ch !== ch.toLowerCase() && ch === ch.toUpperCase();
export const lc = (label) =>
  label.split(/\s+/).filter(Boolean).map((w) => ([...w].filter(isUpper).length > 1 || /\d/.test(w) ? w : w.toLowerCase())).join(" ");
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const joinList = (items) => (items.length <= 1 ? items.join("") : items.slice(0, -1).join(", ") + " and " + items[items.length - 1]);
const sortedUnique = (xs) => [...new Set(xs)].sort();
const byAtId = byKey((r) => [r.at, r.id]);

export class Engine {
  constructor(lexicon) {
    this.parser = new Parser(lexicon);
    this.concepts = this.parser.concepts;
  }

  ask(chart, question) {
    return this.run(chart, this.parser.parse(question, chart.asOf));
  }

  run(chart, query) {
    const concept = query.concept ? this.concepts[query.concept] : null;
    const ans = this[`_${query.intent}`](chart, concept, query.window);
    ans.intent = query.intent;
    ans.concept = query.concept;
    ans.window = query.window;
    ans.text = ans.claims.map((c) => c.text).join(" ");
    return ans;
  }

  _of(chart, type, codes = null, window = null) {
    const cs = codes ? new Set(codes) : null;
    return chart.records.filter((r) => r.type === type && !r.noresult && (!cs || cs.has(r.code)) && (!window || (window.start <= r.date && r.date <= window.end)));
  }

  _answered(claims, result) { return { status: "answered", claims, result }; }
  _notFound(text) { return { status: "not_found", claims: [{ text, cites: [] }], result: {} }; }
  _rank(concept) {
    const order = new Map(concept.codes.map((c, i) => [c, i]));
    return byKey((r) => [r.at, -(order.get(r.code) ?? 0), r.id]);
  }

  _latest_value(chart, concept, window) {
    const rs = this._of(chart, "Observation", concept.codes, window);
    const where = window ? ` ${window.label}` : "";
    if (!rs.length) return this._notFound(`No ${concept.label} results${where} in the record.`);
    rs.sort(this._rank(concept));
    const last = rs[rs.length - 1];
    const claims = [{ text: `${concept.label}${where}: ${fmtValue(last)} on ${fmtDate(last.date)}.`, cites: [last.id] }];
    if (rs.length > 1) {
      const prev = rs[rs.length - 2];
      claims.push({ text: `Before that: ${fmtValue(prev)} on ${fmtDate(prev.date)}.`, cites: [prev.id] });
    }
    if (!window && last.date < minusDays(chart.asOf, 365)) claims.push({ text: "This is the most recent result and it is more than a year old.", cites: [last.id] });
    return this._answered(claims, { id: last.id, date: last.date, value: fmtValue(last) });
  }

  _trend(chart, concept, window) {
    const rs = this._of(chart, "Observation", concept.codes, window);
    const where = window ? ` ${window.label}` : "";
    if (!rs.length) return this._notFound(`No ${concept.label} results${where} in the record.`);
    rs.sort(this._rank(concept));
    const pts = rs.slice(-TREND_POINTS);
    const series = pts.map((r) => `${fmtValue(r)} on ${fmtDate(r.date)}`).join("; ");
    const claims = [{ text: `${concept.label}${where}, ${pts.length === 1 ? "the only result" : `last ${pts.length} results`}: ${series}.`, cites: pts.map((r) => r.id) }];
    let direction = null;
    const a = numeric(pts[0]), b = numeric(pts[pts.length - 1]);
    if (pts.length >= 2 && a !== null && b !== null) {
      const change = a ? (b - a) / Math.abs(a) : 0;
      direction = change > 0.05 ? "rising" : change < -0.05 ? "falling" : "stable";
      const word = { rising: "Rising", falling: "Falling", stable: "Roughly stable" }[direction];
      claims.push({ text: `${word} from ${fmtValue(pts[0])} to ${fmtValue(pts[pts.length - 1])}.`, cites: [pts[0].id, pts[pts.length - 1].id] });
    }
    if (rs.length > pts.length) claims.push({ text: `${rs.length} results on record in total.`, cites: rs.map((r) => r.id) });
    return this._answered(claims, { ids: pts.map((r) => r.id), direction });
  }

  _has_condition(chart, concept) {
    const rs = this._of(chart, "Condition", concept.codes);
    if (!rs.length) return this._answered([{ text: `No ${lc(concept.label)} in the record.`, cites: [] }], { state: "never", codes: [] });
    rs.sort(byAtId);
    if (rs.every((r) => r.status === "recorded")) {
      const last = rs[rs.length - 1].date;
      const recent = rs.filter((r) => r.date === last);
      const names = [];
      for (const r of recent) if (!names.includes(r.name)) names.push(r.name);
      const claims = [{ text: `Yes. ${joinList(names)}, recorded at the hospital stay of ${fmtDate(last)}.`, cites: recent.map((r) => r.id) }];
      if (rs.length > recent.length) claims.push({ text: `${plural(rs.length, "record")} of it in total.`, cites: rs.map((r) => r.id) });
      return this._answered(claims, { state: "recorded", codes: sortedUnique(rs.map((r) => r.code)) });
    }
    const active = rs.filter((r) => r.status === "active");
    if (active.length) {
      const names = [];
      for (const r of active) if (!names.includes(r.name)) names.push(r.name);
      const claims = [{ text: `Yes. ${joinList(names)}, active since ${fmtDate(active[0].date)}.`, cites: active.map((r) => r.id) }];
      return this._answered(claims, { state: "active", codes: sortedUnique(active.map((r) => r.code)) });
    }
    const last = [...rs].sort(byKey((r) => [r.end || r.date, r.at, r.id])).pop();
    let text = `Not currently. ${last.name} was recorded on ${fmtDate(last.date)}`;
    text += last.end ? ` and resolved on ${fmtDate(last.end)}.` : " and is no longer active.";
    const claims = [{ text, cites: [last.id] }];
    if (rs.length > 1) claims.push({ text: `${plural(rs.length, "episode")} on record.`, cites: rs.map((r) => r.id) });
    return this._answered(claims, { state: "resolved", codes: sortedUnique(rs.map((r) => r.code)) });
  }

  _lastStay(records) {
    let best = null;
    for (const r of records) if (r.enc && (!best || r.at > best.at || (r.at === best.at && r.id > best.id))) best = r;
    return best ? best.enc : null;
  }

  _stayItems(rs, enc) {
    const first = new Map();
    for (const r of [...rs].sort(byAtId)) if (r.enc === enc && !first.has(r.code)) first.set(r.code, r);
    return [...first.values()].sort(byAtId);
  }

  _problem_list(chart) {
    if (chart.source === "hospital") {
      const conds = this._of(chart, "Condition");
      const enc = this._lastStay(conds);
      if (!enc) return this._answered([{ text: "No diagnoses in the record.", cites: [] }], { codes: [] });
      const items = this._stayItems(conds, enc);
      const claims = [{ text: `${plural(items.length, "diagnosis")} at the most recent hospital stay, ${fmtDate(items[0].date)}:`.replace("diagnosiss", "diagnoses"), cites: items.map((r) => r.id) }];
      for (const r of items) claims.push({ text: `${r.name};`, cites: [r.id] });
      claims[claims.length - 1].text = claims[claims.length - 1].text.slice(0, -1) + ".";
      return this._answered(claims, { codes: sortedUnique(items.map((r) => r.code)) });
    }
    const rs = this._of(chart, "Condition").filter((r) => r.status === "active");
    if (!rs.length) return this._answered([{ text: "No active problems in the record.", cites: [] }], { codes: [] });
    const first = new Map();
    for (const r of [...rs].sort(byAtId)) if (!first.has(r.code)) first.set(r.code, r);
    const items = [...first.values()].sort(byAtId);
    const claims = [{ text: `${plural(items.length, "active problem")}:`, cites: items.map((r) => r.id) }];
    for (const r of items) claims.push({ text: `${r.name} (since ${fmtDate(r.date)});`, cites: [r.id] });
    claims[claims.length - 1].text = claims[claims.length - 1].text.slice(0, -1) + ".";
    return this._answered(claims, { codes: [...first.keys()].sort() });
  }

  _medSeries(chart, codes) { return this._of(chart, "MedicationRequest", codes).sort(byAtId); }

  _on_med(chart, concept) {
    const rs = this._medSeries(chart, concept.codes);
    if (!rs.length) return this._answered([{ text: `No ${lc(concept.label)} in the record.`, cites: [] }], { state: "never", codes: [] });
    if (chart.source === "hospital") {
      const enc = this._lastStay(this._medSeries(chart, null));
      const hits = enc ? this._stayItems(rs, enc) : [];
      if (hits.length) {
        return this._answered([{ text: `Yes, ordered during the most recent hospital stay: ${joinList(hits.map((r) => r.name))}, from ${fmtDate(hits[0].date)}.`,
          cites: hits.map((r) => r.id).slice(0, 8) }], { state: "last_stay", codes: sortedUnique(hits.map((r) => r.code)) });
      }
      const last = rs[rs.length - 1];
      return this._answered([{ text: `Not during the most recent hospital stay. ${last.name} was last ordered on ${fmtDate(last.date)}.`, cites: [last.id] }],
        { state: "past", codes: [] });
    }
    const active = rs.filter((r) => r.status === "active");
    if (active.length) {
      const claims = [{ text: "Yes.", cites: active.map((r) => r.id) }];
      const seen = [];
      for (const r of active) {
        if (seen.includes(r.code)) continue;
        seen.push(r.code);
        const first = rs.find((x) => x.code === r.code);
        claims.push({ text: `${r.name}, active, first prescribed ${fmtDate(first.date)}.`, cites: [...new Set([r.id, first.id])] });
      }
      return this._answered(claims, { state: "active", codes: [...seen].sort() });
    }
    const last = rs[rs.length - 1];
    return this._answered([{ text: `Not currently. ${last.name} was last prescribed on ${fmtDate(last.date)} and that order is ${last.status}.`, cites: [last.id] }],
      { state: "past", codes: [] });
  }

  _med_list(chart) {
    const rs = this._medSeries(chart, null);
    if (chart.source === "hospital") {
      const enc = this._lastStay(rs);
      if (!enc) return this._answered([{ text: "No medication orders in the record.", cites: [] }], { codes: [] });
      const items = this._stayItems(rs, enc);
      const claims = [{ text: `${plural(items.length, "medication")} ordered during the most recent hospital stay, from ${fmtDate(items[0].date)}:`, cites: items.map((r) => r.id) }];
      for (const r of items) claims.push({ text: `${r.name} (${fmtDate(r.date)});`, cites: [r.id] });
      claims[claims.length - 1].text = claims[claims.length - 1].text.slice(0, -1) + ".";
      return this._answered(claims, { codes: sortedUnique(items.map((r) => r.code)) });
    }
    const active = rs.filter((r) => r.status === "active");
    if (!active.length) return this._answered([{ text: "No active medications in the record.", cites: [] }], { codes: [] });
    const codes = [];
    for (const r of active) if (!codes.includes(r.code)) codes.push(r.code);
    const claims = [{ text: `${plural(codes.length, "active medication")}:`, cites: active.map((r) => r.id) }];
    for (const code of codes) {
      const cur = active.filter((r) => r.code === code).pop();
      const first = rs.find((x) => x.code === code);
      const reason = cur.reason ? `, for ${lc(cur.reason)}` : "";
      claims.push({ text: `${cur.name} (since ${fmtDate(first.date)}${reason});`, cites: [...new Set([cur.id, first.id])] });
    }
    claims[claims.length - 1].text = claims[claims.length - 1].text.slice(0, -1) + ".";
    return this._answered(claims, { codes: [...codes].sort() });
  }

  _med_start(chart, concept) {
    const rs = this._medSeries(chart, concept.codes);
    if (!rs.length) return this._answered([{ text: `No ${lc(concept.label)} in the record.`, cites: [] }], { date: null });
    const first = rs[0], last = rs[rs.length - 1];
    const claims = [{ text: `${first.name} was first prescribed on ${fmtDate(first.date)}.`, cites: [first.id] }];
    if (last.status === "active") claims.push({ text: "It is still active.", cites: [last.id] });
    else if (last !== first) claims.push({ text: `Last prescribed on ${fmtDate(last.date)}, no longer active.`, cites: [last.id] });
    else claims.push({ text: "It is no longer active.", cites: [last.id] });
    return this._answered(claims, { date: first.date });
  }

  _allergies(chart) { return this._of(chart, "AllergyIntolerance").filter((r) => r.status === "active" && !GENERIC_ALLERGY.test(r.name)); }

  _allergyText(r) {
    const bits = [r.category, r.criticality ? `${r.criticality} criticality` : ""].filter(Boolean);
    if (r.reactions && r.reactions.length) bits.push("reaction: " + r.reactions.map(lc).join(", "));
    return r.name + (bits.length ? ` (${bits.join("; ")})` : "");
  }

  _allergy_list(chart) {
    const rs = this._allergies(chart);
    if (!rs.length) return this._answered([{ text: "No allergies recorded.", cites: [] }], { codes: [] });
    const claims = [{ text: `${plural(rs.length, "allergy")}:`.replace("allergys", "allergies"), cites: rs.map((r) => r.id) }];
    for (const r of rs) claims.push({ text: this._allergyText(r) + ";", cites: [r.id] });
    claims[claims.length - 1].text = claims[claims.length - 1].text.slice(0, -1) + ".";
    return this._answered(claims, { codes: sortedUnique(rs.map((r) => r.code)) });
  }

  _allergy_check(chart, concept) {
    const rs = this._allergies(chart);
    const hits = concept.kind === "allergy" ? rs.filter((r) => concept.codes.includes(r.code))
      : rs.filter((r) => concept.phrases.some((w) => r.name.toLowerCase().includes(w)));
    if (!hits.length) return this._answered([{ text: `No ${lc(concept.label)} allergy recorded.`, cites: [] }], { allergic: false });
    return this._answered([{ text: "Yes. " + hits.map((r) => this._allergyText(r)).join("; ") + ".", cites: hits.map((r) => r.id) }], { allergic: true });
  }

  _vaccine_last(chart, concept) {
    const rs = this._of(chart, "Immunization", concept.codes).sort(byAtId);
    if (!rs.length) return this._answered([{ text: `No ${lc(concept.label)} in the record.`, cites: [] }], { date: null });
    const last = rs[rs.length - 1];
    const claims = [{ text: `Last ${lc(concept.label)}: ${fmtDate(last.date)} (${last.name}).`, cites: [last.id] }];
    if (rs.length > 1) claims.push({ text: `${plural(rs.length, "dose")} on record.`, cites: rs.map((r) => r.id) });
    return this._answered(claims, { date: last.date });
  }

  _vaccine_list(chart) {
    const rs = this._of(chart, "Immunization").sort(byAtId);
    if (!rs.length) return this._answered([{ text: "No vaccines recorded.", cites: [] }], {});
    const latest = new Map();
    for (const r of rs) latest.set(r.name, r);
    const claims = [{ text: `${plural(rs.length, "vaccine dose")} on record. Most recent of each:`, cites: rs.map((r) => r.id) }];
    const entries = [...latest.entries()].sort((a, b) => (a[1].at < b[1].at ? 1 : a[1].at > b[1].at ? -1 : 0));
    for (const [name, r] of entries) claims.push({ text: `${name}, ${fmtDate(r.date)};`, cites: [r.id] });
    claims[claims.length - 1].text = claims[claims.length - 1].text.slice(0, -1) + ".";
    return this._answered(claims, {});
  }

  _er_visits(chart, concept, window) {
    const rs = this._of(chart, "Encounter", null, window).filter((r) => r.cls === "EMER");
    if (!rs.length) return this._answered([{ text: `No emergency visits ${window.label}.`, cites: [] }], { count: 0 });
    const dates = rs.map((r) => fmtDate(r.date) + (r.reason ? ` (${lc(r.reason)})` : ""));
    return this._answered([{ text: `${plural(rs.length, "emergency visit")} ${window.label}: ${dates.join("; ")}.`, cites: rs.map((r) => r.id) }], { count: rs.length });
  }

  _admissions(chart, concept, window) {
    const rs = this._of(chart, "Encounter", null, window).filter((r) => r.cls === "IMP");
    if (!rs.length) return this._answered([{ text: `No hospital admissions ${window.label}.`, cites: [] }], { count: 0 });
    return this._answered([{ text: `${plural(rs.length, "hospital admission")} ${window.label}: ${rs.map((r) => `${fmtDate(r.date)} (${lc(r.name)})`).join("; ")}.`,
      cites: rs.map((r) => r.id) }], { count: rs.length });
  }

  _last_visit(chart) {
    const rs = this._of(chart, "Encounter").filter((r) => r.date <= chart.asOf && r.cls !== "ICU"); // an ICU stay is part of an admission
    if (!rs.length) return this._answered([{ text: "No visits in the record.", cites: [] }], { id: null });
    const last = [...rs].sort(byAtId).pop();
    const why = last.reason ? ` for ${lc(last.reason)}` : "";
    return this._answered([{ text: `Last visit on ${fmtDate(last.date)}: ${lc(last.name)}${why}.`, cites: [last.id] }], { id: last.id });
  }

  _age(chart) {
    const years = yearsBetween(chart.birthDate, chart.asOf);
    return this._answered([{ text: `${years} years old, born ${fmtDate(chart.birthDate)}.`, cites: [chart.id] }], { years });
  }

  _advice() {
    return { status: "advice", result: {}, claims: [{ text: "That is a treatment decision, and Circa only reports what the record shows. Ask about current medications, recent labs or the problem list instead.", cites: [] }] };
  }

  _unsupported() {
    return { status: "unsupported", result: {}, claims: [{ text: "The record does not cover that. Circa can answer about labs, vitals, conditions, medications, allergies, vaccines and visits.", cites: [] }] };
  }
}
