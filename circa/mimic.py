"""Real patients: MIMIC-IV Clinical Database Demo on FHIR (100 de-identified patients from Beth Israel
Deaconess Medical Center, ODbL). https://physionet.org/content/mimic-iv-fhir-demo/2.1.0/

Every clinical resource in the release is read: hospital, ED and ICU stays; diagnoses; medication orders,
administrations, dispenses and the home medications reported in the ED; procedures; labs, microbiology,
ICU charting (vitals, assessments, outputs) and ED observations. Only reference data (Location, Organization,
Specimen, MedicationMix) is left out, since it describes things rather than events in a patient's care.

The records are hospital records, which differ from a primary-care chart in three ways that matter here:
  - diagnoses are billing codes attached to a hospital stay, with no onset or resolved date
    (status "recorded", dated by the stay they belong to);
  - medication orders are all completed or stopped, so "current" means ordered during the most recent stay;
  - dates are shifted into the 2100s for privacy, so each chart's "as of" is its own latest record.
Names are not released; patients are shown by their MIMIC subject id.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from .fhir import UNITS, clean, coding, utc

KEEP_LAB_STRINGS = {"50852", "51003"}  # A1c and troponin sometimes arrive as text ('<0.01')

# ICU blood pressure arrives as separate systolic and diastolic items charted at the same minute; they are paired
# into one reading (cited by the systolic resource's id; the raw view shows both resources).
BP_PAIRS = {"220179": ("220180", "Non-invasive blood pressure"), "220050": ("220051", "Arterial blood pressure")}
BP_DIA = {d: s for s, (d, _) in BP_PAIRS.items()}


def _read(folder: Path, name: str):
    path = folder / f"{name}.ndjson.gz"
    if not path.exists():
        return
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def _ref(r: dict, key: str) -> str | None:
    ref = (r.get(key) or {}).get("reference")
    return ref.split("/")[-1] if ref else None


# the same unit is spelled differently by the ED and ICU systems
SAME_UNIT = {"bpm": "/min", "beats/minute": "/min", "insp/min": "/min", "breaths/minute": "/min", "F": "°F", "°F": "°F", "?F": "°F", "C": "°C", "?C": "°C"}


def _qty(q: dict) -> tuple[float, str]:
    unit = q.get("unit") or q.get("code", "")
    unit = SAME_UNIT.get(unit, UNITS.get(unit, unit))
    return round(float(q["value"]), 2), unit


def ingest(folder: Path) -> tuple[list[dict], dict[str, dict]]:
    """Returns (charts, raw) where raw maps record id -> original resource."""
    folder = Path(folder)
    charts: dict[str, dict] = {}
    raw: dict[str, dict] = {}
    for p in _read(folder, "MimicPatient"):
        sid = next((i["value"] for i in p.get("identifier", []) if i.get("system", "").endswith("/patient")), p["id"][:8])
        charts[p["id"]] = {"id": p["id"], "name": f"Patient {sid}", "sex": p.get("gender", ""), "birthDate": p.get("birthDate", ""),
                           "deceased": (p.get("deceasedDateTime") or "")[:10] or None, "source": "hospital", "records": []}

    def add(pid: str | None, rec: dict, res: dict) -> None:
        if pid in charts:
            charts[pid]["records"].append(rec)
            raw[rec["id"]] = {k: v for k, v in res.items() if k != "meta"}

    # encounters: hospital admissions and emergency department visits
    enc_start: dict[str, str] = {}
    for name, cls in (("MimicEncounter", "IMP"), ("MimicEncounterED", "EMER"), ("MimicEncounterICU", "ICU")):
        for e in _read(folder, name):
            start = (e.get("period") or {}).get("start")
            if not start:
                continue
            enc_start[e["id"]] = start
            kind = (e.get("class") or {}).get("display", "")
            label = ("Emergency department visit" if cls == "EMER" else "ICU stay" if cls == "ICU"
                     else f"Hospital admission ({kind})" if kind else "Hospital admission")
            rec = {"id": e["id"], "type": "Encounter", "system": "mimic", "code": cls, "name": label, "at": utc(start), "date": start[:10], "cls": cls}
            if cls == "ICU" and _ref(e, "partOf"):
                rec["enc"] = _ref(e, "partOf")
            add(_ref(e, "subject"), rec, e)

    # diagnoses, dated by their stay
    for name in ("MimicCondition", "MimicConditionED"):
        for c in _read(folder, name):
            enc = _ref(c, "encounter")
            start = enc_start.get(enc or "")
            if not start:
                continue
            system, code, display = coding(c.get("code"))
            add(_ref(c, "subject"), {"id": c["id"], "type": "Condition", "system": "icd", "code": code, "name": clean(display),
                                     "at": utc(start), "date": start[:10], "status": "recorded", "enc": enc}, c)

    # medication orders, named by the hospital formulary
    med_name: dict[str, str] = {}
    for m in _read(folder, "MimicMedication"):
        n = next((i["value"] for i in m.get("identifier", []) if i.get("system", "").endswith("medication-name")), None)
        if n:
            med_name[m["id"]] = n
    req: dict[str, tuple[str, str]] = {}  # request id -> (name, authoredOn)
    for r in _read(folder, "MimicMedicationRequest"):
        name = med_name.get(_ref(r, "medicationReference") or "") or (r.get("medicationCodeableConcept") or {}).get("text")
        if not name or not r.get("authoredOn"):
            continue
        req[r["id"]] = (name, r["authoredOn"])
        ts = r["authoredOn"]
        add(_ref(r, "subject"), {"id": r["id"], "type": "MedicationRequest", "system": "mimic-name", "code": " ".join(name.lower().split()),
                                 "name": name, "at": utc(ts), "date": ts[:10], "status": r.get("status", ""), "enc": _ref(r, "encounter")}, r)

    # labs and emergency department vital signs
    for o in _read(folder, "MimicObservationLabevents"):
        ts = o.get("effectiveDateTime")
        system, code, display = coding(o.get("code"))
        if not ts:
            continue
        rec = {"id": o["id"], "type": "Observation", "cat": "lab", "system": "mimic-lab", "code": code, "name": display, "at": utc(ts), "date": ts[:10]}
        if "valueQuantity" in o and "value" in o["valueQuantity"]:
            rec["value"], rec["unit"] = _qty(o["valueQuantity"])
        elif code in KEEP_LAB_STRINGS and o.get("valueString"):
            rec["text"] = o["valueString"]
        else:
            continue
        add(_ref(o, "subject"), rec, o)
    for o in _read(folder, "MimicObservationVitalSignsED"):
        ts = o.get("effectiveDateTime")
        system, code, display = coding(o.get("code"))
        if not ts:
            continue
        rec = {"id": o["id"], "type": "Observation", "cat": "vital", "system": system, "code": code, "name": display, "at": utc(ts), "date": ts[:10]}
        if "valueQuantity" in o:
            rec["value"], rec["unit"] = _qty(o["valueQuantity"])
        elif "component" in o:
            parts = [[coding(c.get("code"))[1], coding(c.get("code"))[2], *_qty(c["valueQuantity"])] for c in o["component"] if "valueQuantity" in c]
            if not parts:
                continue
            rec["parts"] = parts
        else:
            continue
        add(_ref(o, "subject"), rec, o)

    # medicines given, handed out, or reported as taken at home
    def med_label(cc: dict | None) -> str | None:
        cc = cc or {}
        if cc.get("text"):
            return cc["text"]
        for c in cc.get("coding", []):
            if c.get("display"):
                return c["display"]
            if c.get("system", "").endswith("medication-name"):
                return c["code"]
        return None

    for name in ("MimicMedicationAdministration", "MimicMedicationAdministrationICU"):
        for m in _read(folder, name):
            ts = m.get("effectiveDateTime") or (m.get("effectivePeriod") or {}).get("start")
            label = med_label(m.get("medicationCodeableConcept")) or req.get(_ref(m, "request") or "", (None,))[0]
            if not ts or not label:
                continue
            rec = {"id": m["id"], "type": "MedicationAdministration", "system": "mimic-name", "code": " ".join(label.lower().split()),
                   "name": label, "at": utc(ts), "date": ts[:10], "status": m.get("status", ""), "enc": _ref(m, "context")}
            dose = (m.get("dosage") or {}).get("dose")
            if dose and "value" in dose:
                rec["value"], rec["unit"] = _qty(dose)
            add(_ref(m, "subject"), rec, m)
    for name in ("MimicMedicationDispense", "MimicMedicationDispenseED"):
        for m in _read(folder, name):
            presc = next((_ref({"r": x}, "r") for x in m.get("authorizingPrescription", [])), None)
            ts = m.get("whenHandedOver") or m.get("whenPrepared") or req.get(presc or "", (None, None))[1]
            label = med_label(m.get("medicationCodeableConcept")) or req.get(presc or "", (None,))[0]
            if not ts or not label:
                continue
            add(_ref(m, "subject"), {"id": m["id"], "type": "MedicationDispense", "system": "mimic-name", "code": " ".join(label.lower().split()),
                                     "name": label, "at": utc(ts), "date": ts[:10], "status": m.get("status", ""), "enc": _ref(m, "context")}, m)
    for m in _read(folder, "MimicMedicationStatementED"):
        ts = m.get("dateAsserted")
        label = med_label(m.get("medicationCodeableConcept"))
        if not ts or not label:
            continue
        add(_ref(m, "subject"), {"id": m["id"], "type": "MedicationStatement", "system": "mimic-name", "code": " ".join(label.lower().split()),
                                 "name": label, "at": utc(ts), "date": ts[:10], "status": "reported at ED visit", "enc": _ref(m, "context")}, m)

    # procedures: billed hospital procedures, ICU lines and devices, ED triage and assessments
    for name in ("MimicProcedure", "MimicProcedureICU", "MimicProcedureED"):
        for pr in _read(folder, name):
            ts = pr.get("performedDateTime") or (pr.get("performedPeriod") or {}).get("start")
            system, code, display = coding(pr.get("code"))
            if not ts or not display:
                continue
            add(_ref(pr, "subject"), {"id": pr["id"], "type": "Procedure", "system": "mimic", "code": code, "name": clean(display),
                                      "at": utc(ts), "date": ts[:10], "enc": _ref(pr, "encounter")}, pr)

    # ICU charting: vitals, assessments, device settings, outputs and charted dates
    pending_bp: dict[tuple, dict] = {}
    for name, cat in (("MimicObservationChartevents", None), ("MimicObservationOutputevents", "output"), ("MimicObservationDatetimeevents", "icu")):
        for o in _read(folder, name):
            ts = o.get("effectiveDateTime")
            system, code, display = coding(o.get("code"))
            if not ts or not display:
                continue
            group = ((o.get("category") or [{}])[0].get("coding") or [{}])[0].get("code", "")
            rec = {"id": o["id"], "type": "Observation", "cat": cat or ("vital" if group == "Routine Vital Signs" else "icu"),
                   "system": "mimic-icu", "code": code, "name": display, "at": utc(ts), "date": ts[:10]}
            if group:
                rec["group"] = group
            if "valueQuantity" in o and "value" in o["valueQuantity"]:
                rec["value"], rec["unit"] = _qty(o["valueQuantity"])
            elif o.get("valueString"):
                rec["text"] = " ".join(o["valueString"].split())
            elif o.get("valueDateTime"):
                rec["text"] = o["valueDateTime"][:10]
            else:
                continue
            pid = _ref(o, "subject")
            if code in BP_PAIRS or code in BP_DIA:
                if "value" not in rec:
                    continue
                sys_code = code if code in BP_PAIRS else BP_DIA[code]
                key = (pid, sys_code, ts)
                other = pending_bp.pop(key, None)
                if other is None:
                    pending_bp[key] = (rec, o)
                    continue
                (r1, o1), (r2, o2) = (other, (rec, o)) if other[0]["code"] == sys_code else ((rec, o), other)
                pair = {"id": r1["id"], "type": "Observation", "cat": "vital", "system": "mimic-icu", "code": sys_code,
                        "name": BP_PAIRS[sys_code][1], "at": r1["at"], "date": r1["date"], "group": group,
                        "parts": [["8480-6", "Systolic blood pressure", r1["value"], r1["unit"]],
                                  ["8462-4", "Diastolic blood pressure", r2["value"], r2["unit"]]]}
                if pid in charts:
                    charts[pid]["records"].append(pair)
                    raw[pair["id"]] = [{k: v for k, v in x.items() if k != "meta"} for x in (o1, o2)]
                continue
            add(pid, rec, o)
    for (pid, _, _), (rec, o) in pending_bp.items():  # a systolic or diastolic charted alone stays as it is
        add(pid, rec, o)

    # ED observations (pain, triage notes) and microbiology
    for o in _read(folder, "MimicObservationED"):
        ts = o.get("effectiveDateTime")
        system, code, display = coding(o.get("code"))
        if not ts or not o.get("valueString"):
            continue
        add(_ref(o, "subject"), {"id": o["id"], "type": "Observation", "cat": "ed", "system": system, "code": code, "name": display,
                                 "at": utc(ts), "date": ts[:10], "text": " ".join(o["valueString"].split())}, o)
    owner: dict[str, str] = {}
    for name in ("MimicObservationMicroTest", "MimicObservationMicroOrg", "MimicObservationMicroSusc"):
        for o in _read(folder, name):
            ts = o.get("effectiveDateTime")
            system, code, display = coding(o.get("code"))
            pid = _ref(o, "subject") or next((owner.get(_ref({"r": d}, "r")) for d in o.get("derivedFrom", [])), None)
            owner[o["id"]] = pid
            if not ts or not display:
                continue
            value = o.get("valueString") or coding(o.get("valueCodeableConcept"))[2] or ("organism grown" if name.endswith("Org") else "")
            if not value:
                continue
            kind = {"MimicObservationMicroTest": "Culture or test", "MimicObservationMicroOrg": "Organism", "MimicObservationMicroSusc": "Antibiotic"}[name]
            add(pid, {"id": o["id"], "type": "Observation", "cat": "micro", "system": "mimic-micro", "code": code,
                      "name": f"{kind}: {clean(display)}", "at": utc(ts), "date": ts[:10], "text": " ".join(value.split())}, o)

    out = []
    for c in charts.values():
        if not c["records"]:
            continue
        c["records"].sort(key=lambda x: (x["at"], x["type"], x["code"], x["id"]))
        c["asOf"] = max(r["date"] for r in c["records"])
        out.append(c)
    out.sort(key=lambda c: c["id"])
    return out, raw
