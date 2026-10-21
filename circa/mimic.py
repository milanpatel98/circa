"""Real patients: MIMIC-IV Clinical Database Demo on FHIR (100 de-identified patients from Beth Israel
Deaconess Medical Center, ODbL). https://physionet.org/content/mimic-iv-fhir-demo/2.1.0/

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


def _qty(q: dict) -> tuple[float, str]:
    unit = q.get("unit") or q.get("code", "")
    return round(float(q["value"]), 2), UNITS.get(unit, unit)


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
    for name, cls in (("MimicEncounter", "IMP"), ("MimicEncounterED", "EMER")):
        for e in _read(folder, name):
            start = (e.get("period") or {}).get("start")
            if not start:
                continue
            enc_start[e["id"]] = start
            kind = (e.get("class") or {}).get("display", "")
            label = "Emergency department visit" if cls == "EMER" else f"Hospital admission ({kind})" if kind else "Hospital admission"
            add(_ref(e, "subject"), {"id": e["id"], "type": "Encounter", "system": "mimic", "code": cls, "name": label,
                                     "at": utc(start), "date": start[:10], "cls": cls}, e)

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
    for r in _read(folder, "MimicMedicationRequest"):
        name = med_name.get(_ref(r, "medicationReference") or "") or (r.get("medicationCodeableConcept") or {}).get("text")
        if not name or not r.get("authoredOn"):
            continue
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

    out = []
    for c in charts.values():
        if not c["records"]:
            continue
        c["records"].sort(key=lambda x: (x["at"], x["type"], x["code"], x["id"]))
        c["asOf"] = max(r["date"] for r in c["records"])
        out.append(c)
    out.sort(key=lambda c: c["id"])
    return out, raw
