"""Query + chart -> answer. Every sentence in an answer carries the ids of the records it rests on.

An answer is a dict:
    status   answered | not_found | advice | unsupported
    intent   what was asked (see parse.py)
    claims   [{"text": ..., "cites": [record ids]}]  the answer, sentence by sentence
    result   the same answer as data, used for grading
"""

from __future__ import annotations

import re

from .parse import Parser

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
GENERIC_ALLERGY = re.compile(r"disposition|allergy to substance", re.I)
TREND_POINTS = 6


def fmt_date(iso: str) -> str:
    return f"{MONTHS[int(iso[5:7]) - 1]} {int(iso[8:10])}, {iso[:4]}"


def fmt_num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def fmt_value(r: dict) -> str:
    """'6.1 %', '128/82 mmHg', 'Never smoked tobacco'."""
    if "parts" in r:
        sys_ = next((p for p in r["parts"] if p[0] == "8480-6"), None)
        dia = next((p for p in r["parts"] if p[0] == "8462-4"), None)
        if sys_ and dia:
            return f"{fmt_num(sys_[2])}/{fmt_num(dia[2])} {sys_[3]}".strip()
        return ", ".join(f"{p[1]} {fmt_num(p[2])} {p[3]}".strip() for p in r["parts"])
    if "value" in r:
        unit = r.get("unit", "")
        return f"{fmt_num(r['value'])} {unit}".strip() if unit != "%" else f"{fmt_num(r['value'])}%"
    return clean_text(r.get("text", ""))


def clean_text(t: str) -> str:
    return re.sub(r"\s*\((finding|qualifier value|disorder|organism)\)$", "", t)


def numeric(r: dict) -> float | None:
    if "parts" in r:
        sys_ = next((p for p in r["parts"] if p[0] == "8480-6"), None)
        return sys_[2] if sys_ else None
    return r.get("value")


def years_between(birth: str, as_of: str) -> int:
    y = int(as_of[:4]) - int(birth[:4])
    if as_of[5:] < birth[5:]:
        y -= 1
    return y


def lc(label: str) -> str:
    """Lowercase a label for use mid-sentence, keeping acronyms: 'COVID-19 vaccine' stays, 'Influenza vaccine' -> 'influenza vaccine'."""
    return " ".join(w if sum(ch.isupper() for ch in w) > 1 or any(ch.isdigit() for ch in w) else w.lower() for w in label.split())


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def join_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class Engine:
    def __init__(self, lexicon: dict):
        self.parser = Parser(lexicon)
        self.concepts = self.parser.concepts

    def ask(self, chart: dict, question: str) -> dict:
        query = self.parser.parse(question, chart["asOf"])
        return self.run(chart, query)

    def run(self, chart: dict, query: dict) -> dict:
        intent = query["intent"]
        concept = self.concepts.get(query["concept"]) if query["concept"] else None
        handler = getattr(self, f"_{intent}")
        ans = handler(chart, concept, query.get("window"))
        ans["intent"] = intent
        ans["concept"] = query["concept"]
        ans["window"] = query.get("window")
        ans["text"] = " ".join(c["text"] for c in ans["claims"])
        return ans

    # ---- helpers ------------------------------------------------------------------------

    @staticmethod
    def _of(chart: dict, rtype: str, codes: list[str] | None = None, window: dict | None = None) -> list[dict]:
        out = []
        cs = set(codes) if codes is not None else None
        for r in chart["records"]:
            if r["type"] != rtype:
                continue
            if cs is not None and r["code"] not in cs:
                continue
            if window and not (window["start"] <= r["date"] <= window["end"]):
                continue
            out.append(r)
        return out

    @staticmethod
    def _answered(claims: list[dict], result: dict) -> dict:
        return {"status": "answered", "claims": claims, "result": result}

    @staticmethod
    def _not_found(text: str) -> dict:
        return {"status": "not_found", "claims": [{"text": text, "cites": []}], "result": {}}

    @staticmethod
    def _rank(concept: dict):
        order = {c: i for i, c in enumerate(concept["codes"])}
        return lambda r: (r["at"], -order.get(r["code"], 0), r["id"])

    # ---- intents --------------------------------------------------------------------------

    def _latest_value(self, chart, concept, window):
        rs = self._of(chart, "Observation", concept["codes"], window)
        where = f" {window['label']}" if window else ""
        if not rs:
            return self._not_found(f"No {concept['label']} results{where} in the record.")
        rs.sort(key=self._rank(concept))
        last = rs[-1]
        claims = [{"text": f"{concept['label']}{where}: {fmt_value(last)} on {fmt_date(last['date'])}.", "cites": [last["id"]]}]
        if len(rs) > 1:
            prev = rs[-2]
            claims.append({"text": f"Before that: {fmt_value(prev)} on {fmt_date(prev['date'])}.", "cites": [prev["id"]]})
        if not window and last["date"] < _minus_days(chart["asOf"], 365):
            claims.append({"text": "This is the most recent result and it is more than a year old.", "cites": [last["id"]]})
        return self._answered(claims, {"id": last["id"], "date": last["date"], "value": fmt_value(last)})

    def _trend(self, chart, concept, window):
        rs = self._of(chart, "Observation", concept["codes"], window)
        where = f" {window['label']}" if window else ""
        if not rs:
            return self._not_found(f"No {concept['label']} results{where} in the record.")
        rs.sort(key=self._rank(concept))
        pts = rs[-TREND_POINTS:]
        series = "; ".join(f"{fmt_value(r)} on {fmt_date(r['date'])}" for r in pts)
        head = f"{concept['label']}{where}, {'the only result' if len(pts) == 1 else f'last {len(pts)} results'}: {series}."
        claims = [{"text": head, "cites": [r["id"] for r in pts]}]
        direction = None
        a, b = numeric(pts[0]), numeric(pts[-1])
        if len(pts) >= 2 and a is not None and b is not None:
            change = (b - a) / abs(a) if a else 0.0
            direction = "rising" if change > 0.05 else "falling" if change < -0.05 else "stable"
            word = {"rising": "Rising", "falling": "Falling", "stable": "Roughly stable"}[direction]
            claims.append({"text": f"{word} from {fmt_value(pts[0])} to {fmt_value(pts[-1])}.", "cites": [pts[0]["id"], pts[-1]["id"]]})
        if len(rs) > len(pts):
            claims.append({"text": f"{len(rs)} results on record in total.", "cites": [r["id"] for r in rs]})
        return self._answered(claims, {"ids": [r["id"] for r in pts], "direction": direction})

    def _has_condition(self, chart, concept, window):
        rs = self._of(chart, "Condition", concept["codes"])
        label = concept["label"]
        if not rs:
            return self._answered([{"text": f"No {lc(label)} in the record.", "cites": []}],
                                  {"state": "never", "codes": []})
        rs.sort(key=lambda r: (r["at"], r["id"]))
        if all(r["status"] == "recorded" for r in rs):  # hospital billing diagnoses: dated by stay, never resolved
            last = rs[-1]["date"]
            recent = [r for r in rs if r["date"] == last]
            names = []
            for r in recent:
                if r["name"] not in names:
                    names.append(r["name"])
            claims = [{"text": f"Yes. {join_list(names)}, recorded at the hospital stay of {fmt_date(last)}.", "cites": [r["id"] for r in recent]}]
            if len(rs) > len(recent):
                claims.append({"text": f"{plural(len(rs), 'record')} of it in total.", "cites": [r["id"] for r in rs]})
            return self._answered(claims, {"state": "recorded", "codes": sorted({r["code"] for r in rs})})
        active = [r for r in rs if r["status"] == "active"]
        if active:
            names = []
            for r in active:
                if r["name"] not in names:
                    names.append(r["name"])
            since = active[0]
            claims = [{"text": f"Yes. {join_list(names)}, active since {fmt_date(since['date'])}.", "cites": [r["id"] for r in active]}]
            return self._answered(claims, {"state": "active", "codes": sorted({r["code"] for r in active})})
        last = max(rs, key=lambda r: (r.get("end") or r["date"], r["at"], r["id"]))
        text = f"Not currently. {last['name']} was recorded on {fmt_date(last['date'])}"
        text += f" and resolved on {fmt_date(last['end'])}." if last.get("end") else " and is no longer active."
        claims = [{"text": text, "cites": [last["id"]]}]
        if len(rs) > 1:
            claims.append({"text": f"{plural(len(rs), 'episode')} on record.", "cites": [r["id"] for r in rs]})
        return self._answered(claims, {"state": "resolved", "codes": sorted({r["code"] for r in rs})})

    @staticmethod
    def _last_stay(records: list[dict]) -> str | None:
        """The hospital stay of the most recent of these records."""
        rs = [r for r in records if r.get("enc")]
        return max(rs, key=lambda r: (r["at"], r["id"]))["enc"] if rs else None

    def _stay_items(self, rs: list[dict], enc: str) -> list[dict]:
        first: dict[str, dict] = {}
        for r in sorted(rs, key=lambda r: (r["at"], r["id"])):
            if r.get("enc") == enc:
                first.setdefault(r["code"], r)
        return sorted(first.values(), key=lambda r: (r["at"], r["id"]))

    def _problem_list(self, chart, concept, window):
        if chart.get("source") == "hospital":
            conds = self._of(chart, "Condition")
            enc = self._last_stay(conds)
            if not enc:
                return self._answered([{"text": "No diagnoses in the record.", "cites": []}], {"codes": []})
            items = self._stay_items(conds, enc)
            claims = [{"text": f"{plural(len(items), 'diagnosis')} at the most recent hospital stay, {fmt_date(items[0]['date'])}:".replace("diagnosiss", "diagnoses"),
                       "cites": [r["id"] for r in items]}]
            for r in items:
                claims.append({"text": f"{r['name']};", "cites": [r["id"]]})
            claims[-1]["text"] = claims[-1]["text"][:-1] + "."
            return self._answered(claims, {"codes": sorted({r["code"] for r in items})})
        rs = [r for r in self._of(chart, "Condition") if r["status"] == "active"]
        if not rs:
            return self._answered([{"text": "No active problems in the record.", "cites": []}], {"codes": []})
        first: dict[str, dict] = {}
        for r in sorted(rs, key=lambda r: (r["at"], r["id"])):
            first.setdefault(r["code"], r)
        items = sorted(first.values(), key=lambda r: (r["at"], r["id"]))
        claims = [{"text": f"{plural(len(items), 'active problem')}:", "cites": [r["id"] for r in items]}]
        for r in items:
            claims.append({"text": f"{r['name']} (since {fmt_date(r['date'])});", "cites": [r["id"]]})
        claims[-1]["text"] = claims[-1]["text"][:-1] + "."
        return self._answered(claims, {"codes": sorted(first)})

    def _med_series(self, chart, codes):
        return sorted(self._of(chart, "MedicationRequest", codes), key=lambda r: (r["at"], r["id"]))

    def _on_med(self, chart, concept, window):
        rs = self._med_series(chart, concept["codes"])
        label = concept["label"]
        if not rs:
            return self._answered([{"text": f"No {lc(label)} in the record.", "cites": []}], {"state": "never", "codes": []})
        if chart.get("source") == "hospital":
            enc = self._last_stay(self._med_series(chart, None))
            hits = self._stay_items(rs, enc) if enc else []
            if hits:
                claims = [{"text": f"Yes, ordered during the most recent hospital stay: {join_list([r['name'] for r in hits])}, from {fmt_date(hits[0]['date'])}.",
                           "cites": [r["id"] for r in hits][:8]}]
                return self._answered(claims, {"state": "last_stay", "codes": sorted({r["code"] for r in hits})})
            last = rs[-1]
            return self._answered([{"text": f"Not during the most recent hospital stay. {last['name']} was last ordered on {fmt_date(last['date'])}.",
                                    "cites": [last["id"]]}], {"state": "past", "codes": []})
        active = [r for r in rs if r["status"] == "active"]
        if active:
            claims = [{"text": "Yes.", "cites": [r["id"] for r in active]}]
            seen = []
            for r in active:
                if r["code"] in seen:
                    continue
                seen.append(r["code"])
                first = next(x for x in rs if x["code"] == r["code"])
                claims.append({"text": f"{r['name']}, active, first prescribed {fmt_date(first['date'])}.", "cites": list(dict.fromkeys([r["id"], first["id"]]))})
            return self._answered(claims, {"state": "active", "codes": sorted(seen)})
        last = rs[-1]
        claims = [{"text": f"Not currently. {last['name']} was last prescribed on {fmt_date(last['date'])} and that order is {last['status']}.",
                   "cites": [last["id"]]}]
        return self._answered(claims, {"state": "past", "codes": []})

    def _med_list(self, chart, concept, window):
        rs = self._med_series(chart, None)
        if chart.get("source") == "hospital":
            enc = self._last_stay(rs)
            if not enc:
                return self._answered([{"text": "No medication orders in the record.", "cites": []}], {"codes": []})
            items = self._stay_items(rs, enc)
            claims = [{"text": f"{plural(len(items), 'medication')} ordered during the most recent hospital stay, from {fmt_date(items[0]['date'])}:",
                       "cites": [r["id"] for r in items]}]
            for r in items:
                claims.append({"text": f"{r['name']} ({fmt_date(r['date'])});", "cites": [r["id"]]})
            claims[-1]["text"] = claims[-1]["text"][:-1] + "."
            return self._answered(claims, {"codes": sorted({r["code"] for r in items})})
        active = [r for r in rs if r["status"] == "active"]
        if not active:
            return self._answered([{"text": "No active medications in the record.", "cites": []}], {"codes": []})
        codes = []
        for r in active:
            if r["code"] not in codes:
                codes.append(r["code"])
        claims = [{"text": f"{plural(len(codes), 'active medication')}:", "cites": [r["id"] for r in active]}]
        for code in codes:
            cur = [r for r in active if r["code"] == code][-1]
            first = next(x for x in rs if x["code"] == code)
            reason = f", for {lc(cur['reason'])}" if cur.get("reason") else ""
            claims.append({"text": f"{cur['name']} (since {fmt_date(first['date'])}{reason});", "cites": list(dict.fromkeys([cur["id"], first["id"]]))})
        claims[-1]["text"] = claims[-1]["text"][:-1] + "."
        return self._answered(claims, {"codes": sorted(codes)})

    def _med_start(self, chart, concept, window):
        rs = self._med_series(chart, concept["codes"])
        if not rs:
            return self._answered([{"text": f"No {lc(concept['label'])} in the record.", "cites": []}], {"date": None})
        first = rs[0]
        last = rs[-1]
        text = f"{first['name']} was first prescribed on {fmt_date(first['date'])}."
        claims = [{"text": text, "cites": [first["id"]]}]
        if last["status"] == "active":
            claims.append({"text": "It is still active.", "cites": [last["id"]]})
        elif last is not first:
            claims.append({"text": f"Last prescribed on {fmt_date(last['date'])}, no longer active.", "cites": [last["id"]]})
        else:
            claims.append({"text": "It is no longer active.", "cites": [last["id"]]})
        return self._answered(claims, {"date": first["date"]})

    def _allergies(self, chart):
        return [r for r in self._of(chart, "AllergyIntolerance") if r["status"] == "active" and not GENERIC_ALLERGY.search(r["name"])]

    @staticmethod
    def _allergy_text(r: dict) -> str:
        bits = [b for b in (r.get("category"), f"{r['criticality']} criticality" if r.get("criticality") else "") if b]
        if r.get("reactions"):
            bits.append("reaction: " + ", ".join(lc(x) for x in r["reactions"]))
        return f"{r['name']}" + (f" ({'; '.join(bits)})" if bits else "")

    def _allergy_list(self, chart, concept, window):
        rs = self._allergies(chart)
        if not rs:
            return self._answered([{"text": "No allergies recorded.", "cites": []}], {"codes": []})
        claims = [{"text": f"{plural(len(rs), 'allergy')}:".replace("allergys", "allergies"), "cites": [r["id"] for r in rs]}]
        for r in rs:
            claims.append({"text": self._allergy_text(r) + ";", "cites": [r["id"]]})
        claims[-1]["text"] = claims[-1]["text"][:-1] + "."
        return self._answered(claims, {"codes": sorted({r["code"] for r in rs})})

    def _allergy_check(self, chart, concept, window):
        rs = self._allergies(chart)
        if concept["kind"] == "allergy":
            hits = [r for r in rs if r["code"] in concept["codes"]]
        else:  # a drug or substance named outside the allergy vocabulary: match on its name
            words = set(concept["phrases"])
            hits = [r for r in rs if any(w in r["name"].lower() for w in words)]
        label = concept["label"]
        if not hits:
            return self._answered([{"text": f"No {lc(label)} allergy recorded.", "cites": []}], {"allergic": False})
        claims = [{"text": "Yes. " + "; ".join(self._allergy_text(r) for r in hits) + ".", "cites": [r["id"] for r in hits]}]
        return self._answered(claims, {"allergic": True})

    def _vaccine_last(self, chart, concept, window):
        rs = sorted(self._of(chart, "Immunization", concept["codes"]), key=lambda r: (r["at"], r["id"]))
        if not rs:
            return self._answered([{"text": f"No {lc(concept['label'])} in the record.", "cites": []}],
                                  {"date": None})
        last = rs[-1]
        claims = [{"text": f"Last {lc(concept['label'])}: {fmt_date(last['date'])} ({last['name']}).", "cites": [last["id"]]}]
        if len(rs) > 1:
            claims.append({"text": f"{plural(len(rs), 'dose')} on record.", "cites": [r["id"] for r in rs]})
        return self._answered(claims, {"date": last["date"]})

    def _vaccine_list(self, chart, concept, window):
        rs = sorted(self._of(chart, "Immunization"), key=lambda r: (r["at"], r["id"]))
        if not rs:
            return self._answered([{"text": "No vaccines recorded.", "cites": []}], {})
        latest: dict[str, dict] = {}
        for r in rs:
            latest[r["name"]] = r
        claims = [{"text": f"{plural(len(rs), 'vaccine dose')} on record. Most recent of each:", "cites": [r["id"] for r in rs]}]
        for name, r in sorted(latest.items(), key=lambda kv: kv[1]["at"], reverse=True):
            claims.append({"text": f"{name}, {fmt_date(r['date'])};", "cites": [r["id"]]})
        claims[-1]["text"] = claims[-1]["text"][:-1] + "."
        return self._answered(claims, {})

    def _er_visits(self, chart, concept, window):
        rs = [r for r in self._of(chart, "Encounter", None, window) if r["cls"] == "EMER"]
        if not rs:
            return self._answered([{"text": f"No emergency visits {window['label']}.", "cites": []}], {"count": 0})
        dates = [fmt_date(r["date"]) + (f" ({lc(r['reason'])})" if r.get("reason") else "") for r in rs]
        claims = [{"text": f"{plural(len(rs), 'emergency visit')} {window['label']}: {'; '.join(dates)}.", "cites": [r["id"] for r in rs]}]
        return self._answered(claims, {"count": len(rs)})

    def _admissions(self, chart, concept, window):
        rs = [r for r in self._of(chart, "Encounter", None, window) if r["cls"] == "IMP"]
        if not rs:
            return self._answered([{"text": f"No hospital admissions {window['label']}.", "cites": []}], {"count": 0})
        claims = [{"text": f"{plural(len(rs), 'hospital admission')} {window['label']}: {'; '.join(fmt_date(r['date']) + ' (' + lc(r['name']) + ')' for r in rs)}.",
                   "cites": [r["id"] for r in rs]}]
        return self._answered(claims, {"count": len(rs)})

    def _last_visit(self, chart, concept, window):
        rs = [r for r in self._of(chart, "Encounter") if r["date"] <= chart["asOf"]]
        if not rs:
            return self._answered([{"text": "No visits in the record.", "cites": []}], {"id": None})
        last = max(rs, key=lambda r: (r["at"], r["id"]))
        why = f" for {lc(last['reason'])}" if last.get("reason") else ""
        claims = [{"text": f"Last visit on {fmt_date(last['date'])}: {lc(last['name'])}{why}.", "cites": [last["id"]]}]
        return self._answered(claims, {"id": last["id"]})

    def _age(self, chart, concept, window):
        years = years_between(chart["birthDate"], chart["asOf"])
        claims = [{"text": f"{years} years old, born {fmt_date(chart['birthDate'])}.", "cites": [chart["id"]]}]
        return self._answered(claims, {"years": years})

    def _advice(self, chart, concept, window):
        return {"status": "advice", "result": {}, "claims": [{"text": "That is a treatment decision, and Circa only reports what the record shows. "
                                                             "Ask about current medications, recent labs or the problem list instead.", "cites": []}]}

    def _unsupported(self, chart, concept, window):
        return {"status": "unsupported", "result": {}, "claims": [{"text": "The record does not cover that. Circa can answer about labs, vitals, conditions, "
                                                                   "medications, allergies, vaccines and visits.", "cites": []}]}


def _minus_days(iso: str, days: int) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(iso) - timedelta(days=days)).isoformat()
