"""Check an answer against the record it cites. Works on any answerer's output, including a language model's.

A claim passes when:
  - every id it cites exists in this patient's record, and
  - every number and date in its text can be found in the records it cites
    (a value, a blood pressure component, a date, the patient's birth date and age, or a count of the cited records).
Numbers the question itself contained ("in 2021", "past 12 months") are allowed, because they are not claims about the record.
Claims with numbers or dates but no citations fail.
"""

from __future__ import annotations

import re

from .engine import MONTHS, fmt_num, years_between

DATE_TEXT = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),\s+(\d{4})\b")
DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")


def facts(chart: dict, rec: dict | None, cited_count: int) -> tuple[set[str], set[str]]:
    """(numbers, dates) a cited record can back."""
    nums: set[str] = {str(cited_count)}
    dates: set[str] = set()
    if rec is None:
        return nums, dates
    if rec.get("_patient"):
        dates.add(chart["birthDate"])
        nums.add(str(years_between(chart["birthDate"], chart["asOf"])))
        return nums, dates
    for k in ("date", "end"):
        if rec.get(k):
            dates.add(rec[k])
    if "value" in rec:
        nums.add(fmt_num(rec["value"]))
    for p in rec.get("parts", []):
        nums.add(fmt_num(p[2]))
        nums.update(NUMBER.findall(p[3] or ""))
    # numbers written into the record's own name or text ('lisinopril 10 MG', 'stage 3') are part of what it says
    for t in (rec.get("name", ""), rec.get("text", ""), rec.get("reason", ""), rec.get("unit", "")):
        nums.update(NUMBER.findall(t or ""))
    return nums, dates


def check(chart: dict, answer: dict, question: str = "") -> dict:
    index = {r["id"]: r for r in chart["records"]}
    index[chart["id"]] = {"_patient": True}
    allowed_q = set(NUMBER.findall(question))
    # the time frame the answer restates ('in the past 12 months') comes from the question, not the record
    allowed_q |= set(NUMBER.findall(((answer.get("window") or {}).get("label")) or ""))
    problems = []
    for i, claim in enumerate(answer.get("claims", [])):
        text = claim.get("text", "")
        cites = claim.get("cites", [])
        missing = [c for c in cites if c not in index]
        if missing:
            problems.append({"claim": i, "kind": "unknown citation", "detail": ", ".join(missing)})
        nums: set[str] = set()
        dates: set[str] = set()
        for c in cites:
            n, d = facts(chart, index.get(c), len(cites))
            nums |= n
            dates |= d
        # distinct record types/codes among the cited records can also be counted ('3 active medications')
        nums.add(str(len({index[c].get("code") for c in cites if c in index})))
        years = {d[:4] for d in dates}
        stripped = text
        for m in list(DATE_TEXT.finditer(text)):
            iso = f"{m.group(3)}-{MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}"
            if iso not in dates:
                problems.append({"claim": i, "kind": "date not in cited records", "detail": m.group(0)})
            stripped = stripped.replace(m.group(0), " ")
        for m in list(DATE_ISO.finditer(stripped)):
            if m.group(0) not in dates:
                problems.append({"claim": i, "kind": "date not in cited records", "detail": m.group(0)})
            stripped = stripped.replace(m.group(0), " ")
        unbacked = []
        for n in NUMBER.findall(stripped):
            if n in allowed_q:
                continue
            if cites and (n in nums or n in years or fmt_num(float(n)) in nums):
                continue
            unbacked.append(n)
        if cites:
            for n in unbacked:
                problems.append({"claim": i, "kind": "number not in cited records", "detail": n})
        elif (unbacked or DATE_TEXT.search(text)) and answer.get("status") == "answered":
            problems.append({"claim": i, "kind": "uncited claim", "detail": text[:80]})
    return {"ok": not problems, "problems": problems}
