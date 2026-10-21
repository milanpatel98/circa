"""Expected answers, computed straight from the chart.

Deliberately written separately from engine.py, with plain loops and no shared helpers, so a bug in the
engine shows up as a disagreement instead of being copied into the answer key.
"""

from __future__ import annotations

GENERIC_ALLERGY_WORDS = ("disposition", "allergy to substance")


def _rank_key(codes):
    def key(r):
        rank = codes.index(r["code"]) if r["code"] in codes else 0
        return (r["at"], -rank, r["id"])
    return key


def observations(chart, codes, start=None, end=None):
    out = []
    for r in chart["records"]:
        if r["type"] == "Observation" and r["code"] in codes:
            if start and r["date"] < start:
                continue
            if end and r["date"] > end:
                continue
            out.append(r)
    out.sort(key=_rank_key(codes))
    return out


def latest(chart, codes, start=None, end=None):
    rs = observations(chart, codes, start, end)
    return rs[-1]["id"] if rs else None


def trend(chart, codes, n=6):
    rs = observations(chart, codes)[-n:]
    direction = None
    def num(r):
        if "parts" in r:
            for p in r["parts"]:
                if p[0] == "8480-6":
                    return p[2]
            return None
        return r.get("value")
    if len(rs) >= 2 and num(rs[0]) is not None and num(rs[-1]) is not None:
        a, b = num(rs[0]), num(rs[-1])
        change = (b - a) / abs(a) if a else 0.0
        direction = "rising" if change > 0.05 else ("falling" if change < -0.05 else "stable")
    return [r["id"] for r in rs], direction


def condition_state(chart, codes):
    rs = [r for r in chart["records"] if r["type"] == "Condition" and r["code"] in codes]
    if not rs:
        return "never", []
    act = sorted({r["code"] for r in rs if r["status"] == "active"})
    if act:
        return "active", act
    return "resolved", sorted({r["code"] for r in rs})


def active_problems(chart):
    return sorted({r["code"] for r in chart["records"] if r["type"] == "Condition" and r["status"] == "active"})


def med_state(chart, codes):
    rs = [r for r in chart["records"] if r["type"] == "MedicationRequest" and r["code"] in codes]
    if not rs:
        return "never", []
    act = sorted({r["code"] for r in rs if r["status"] == "active"})
    return ("active", act) if act else ("past", [])


def active_meds(chart):
    return sorted({r["code"] for r in chart["records"] if r["type"] == "MedicationRequest" and r["status"] == "active"})


def med_start(chart, codes):
    dates = sorted((r["at"], r["id"], r["date"]) for r in chart["records"] if r["type"] == "MedicationRequest" and r["code"] in codes)
    return dates[0][2] if dates else None


def allergies(chart):
    return sorted({r["code"] for r in chart["records"] if r["type"] == "AllergyIntolerance" and r["status"] == "active"
                   and not any(w in r["name"].lower() for w in GENERIC_ALLERGY_WORDS)})


def last_vaccine(chart, codes):
    rs = sorted((r["at"], r["id"], r["date"]) for r in chart["records"] if r["type"] == "Immunization" and r["code"] in codes)
    return rs[-1][2] if rs else None


def er_count(chart, start, end):
    return sum(1 for r in chart["records"] if r["type"] == "Encounter" and r["cls"] == "EMER" and start <= r["date"] <= end)


def last_visit(chart):
    rs = sorted((r["at"], r["id"]) for r in chart["records"] if r["type"] == "Encounter" and r["date"] <= chart["asOf"])
    return rs[-1][1] if rs else None


def age(chart):
    b, a = chart["birthDate"], chart["asOf"]
    years = int(a[:4]) - int(b[:4])
    if (int(a[5:7]), int(a[8:10])) < (int(b[5:7]), int(b[8:10])):
        years -= 1
    return years
