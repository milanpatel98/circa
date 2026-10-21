"""Claude as the answerer: it reads the chart only through tools, and must answer through a tool that
requires citations. The same benchmark and the same checker then score it.

    export ANTHROPIC_API_KEY=...
    circa bench --answerer claude --limit 10

Set CIRCA_MODEL to choose the model. Nothing here runs without a key.
"""

from __future__ import annotations

import json
import os
import urllib.request

from .engine import fmt_value
from .rag import BM25, render
from .lexicon import norm

SYSTEM = """You answer questions about one patient's medical record for a clinician. Use the tools to read the record.
Rules:
- Only state what the record shows. Every sentence with a fact must cite the record ids it comes from.
- Copy numbers and dates exactly as the record gives them.
- If the record has nothing on the topic, answer with status "not_found". If the question is outside what a record of labs, vitals,
  conditions, medications, allergies, vaccines and visits can show, use "unsupported". If it asks for a treatment decision, use "advice".
- Today is the record's as-of date. "Current" medications and conditions are those with status active.
Finish by calling the answer tool exactly once."""

RESULT_HELP = """Also fill `result` for grading, by intent:
latest_value {id} · trend {ids (oldest first, up to 6), direction rising|falling|stable} · has_condition {state active|resolved|never, codes (active codes)}
problem_list {codes} · on_med {state active|past|never, codes (active codes)} · med_list {codes} · med_start {date} · allergy_list {codes}
allergy_check {allergic} · vaccine_last {date or null} · er_visits {count} · last_visit {id} · age {years}"""

TOOLS = [
    {"name": "patient", "description": "Name, sex, birth date and the record's as-of date.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "search", "description": "Keyword search over every record. Returns up to 25 lines: id, date, type, text.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "records", "description": "List records of one type, newest first (up to 60). Optional filters: name contains text, date range, status.",
     "input_schema": {"type": "object", "properties": {
         "type": {"type": "string", "enum": ["Observation", "Condition", "MedicationRequest", "AllergyIntolerance", "Immunization", "Encounter", "Procedure"]},
         "name": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "status": {"type": "string"}}, "required": ["type"]}},
    {"name": "answer", "description": "Give the final answer. " + RESULT_HELP,
     "input_schema": {"type": "object", "properties": {
         "status": {"type": "string", "enum": ["answered", "not_found", "unsupported", "advice"]},
         "intent": {"type": "string"},
         "claims": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "cites": {"type": "array", "items": {"type": "string"}}},
                                                 "required": ["text", "cites"]}},
         "result": {"type": "object"}}, "required": ["status", "claims"]}},
]


def _line(r: dict) -> dict:
    out = {"id": r["id"], "date": r["date"], "type": r["type"], "name": r["name"], "code": r["code"]}
    if r["type"] == "Observation":
        out["value"] = fmt_value(r)
    for k in ("status", "end", "cls", "reason", "category", "criticality"):
        if r.get(k):
            out[k] = r[k]
    return out


def run_tool(chart: dict, name: str, args: dict, index: BM25) -> object:
    if name == "patient":
        return {k: chart[k] for k in ("id", "name", "sex", "birthDate", "asOf")}
    if name == "search":
        hits = index.top([t for t in norm(args.get("query", "")).split()], 25)
        return [_line(chart["records"][i]) for i in hits]
    if name == "records":
        rs = [r for r in chart["records"] if r["type"] == args["type"]]
        if args.get("name"):
            rs = [r for r in rs if args["name"].lower() in r["name"].lower()]
        if args.get("start"):
            rs = [r for r in rs if r["date"] >= args["start"]]
        if args.get("end"):
            rs = [r for r in rs if r["date"] <= args["end"]]
        if args.get("status"):
            rs = [r for r in rs if r.get("status") == args["status"]]
        return [_line(r) for r in sorted(rs, key=lambda r: r["at"], reverse=True)[:60]]
    return {"error": f"unknown tool {name}"}


def http_transport(body: dict) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("Set ANTHROPIC_API_KEY to use the Claude answerer.")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


class ClaudeAnswerer:
    def __init__(self, transport=http_transport, model: str | None = None, max_turns: int = 8):
        self.transport = transport
        self.model = model or os.environ.get("CIRCA_MODEL", "claude-sonnet-5-5")
        self.max_turns = max_turns
        self._index: dict[str, BM25] = {}

    def ask(self, chart: dict, question: str) -> dict:
        if chart["id"] not in self._index:
            self._index = {chart["id"]: BM25([norm(render(r)).split() for r in chart["records"]])}
        index = self._index[chart["id"]]
        messages = [{"role": "user", "content": question}]
        for _ in range(self.max_turns):
            resp = self.transport({"model": self.model, "max_tokens": 1500, "system": SYSTEM, "tools": TOOLS, "messages": messages})
            messages.append({"role": "assistant", "content": resp["content"]})
            results = []
            for block in resp["content"]:
                if block.get("type") != "tool_use":
                    continue
                if block["name"] == "answer":
                    a = block["input"]
                    ans = {"status": a.get("status"), "intent": a.get("intent"), "claims": a.get("claims", []), "result": a.get("result", {})}
                    ans["text"] = " ".join(c.get("text", "") for c in ans["claims"])
                    return ans
                out = run_tool(chart, block["name"], block.get("input", {}), index)
                results.append({"type": "tool_result", "tool_use_id": block["id"], "content": json.dumps(out)[:20000]})
            if not results:
                break
            messages.append({"role": "user", "content": results})
        return {"status": "unsupported", "intent": None, "claims": [{"text": "No answer.", "cites": []}], "result": {}, "text": "No answer."}
