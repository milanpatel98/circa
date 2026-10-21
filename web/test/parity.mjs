// Every benchmark question for every patient on the site, answered in JavaScript, must match Python exactly.
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { Engine } from "../src/circa.js";

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const lexicon = read("../public/data/lexicon.json");
const expected = read("./expected.json");
const engine = new Engine(lexicon);
const charts = {};
let bad = 0;
for (const { patient, question, answer } of expected) {
  charts[patient] ??= JSON.parse(gunzipSync(readFileSync(new URL(`../public/data/p/${patient}.json.gz`, import.meta.url)))).chart;
  const got = engine.ask(charts[patient], question);
  const pick = (a) => JSON.stringify({ status: a.status, intent: a.intent, concept: a.concept, window: a.window, claims: a.claims, result: a.result, text: a.text });
  if (pick(got) !== pick(answer)) {
    bad++;
    if (bad <= 5) console.error(`MISMATCH ${question}\n  py: ${pick(answer)}\n  js: ${pick(got)}`);
  }
}
console.log(`${expected.length - bad}/${expected.length} answers match Python`);
process.exit(bad ? 1 : 0);
