"""Turn a FHIR R4 patient bundle into a chart: one flat, time-ordered list of clinical records.

Every record keeps the id of the FHIR resource it came from, so any answer built on it can
point back to the exact source. Billing resources (Claim, ExplanationOfBenefit) and
provenance are dropped; they say nothing clinical.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

AS_OF = "2026-10-20"  # the date the synthetic records run up to (see scripts/generate.sh)

# Synthea records social circumstances (employment, education, housing...) as Condition
# resources. They are not diagnoses, so they stay out of the problem list.
SOCIAL = re.compile(
    r"employment|labor force|unemployed|education|social isolation|social contact|^stress|"
    r"criminal record|violence|intimate partner|housing|homeless|transport|refugee|"
    r"military service|risk activity|medication review due|misuses drugs|certificate|equivalency|received higher|"
    r"lack of access|unhealthy alcohol|stopped smoking|smokes tobacco|social|in labor force|part-time|full-time",
    re.I,
)

TAG = re.compile(r"\s*\((disorder|finding|situation|morphologic abnormality|person|procedure|"
                 r"regime/therapy|substance|organism|qualifier value|environment|record artifact)\)$")

# Observation codes kept outside the lab and vital-sign categories.
KEEP_SOCIAL_OBS = {"72166-2", "82810-3"}  # tobacco smoking status, pregnancy status


def clean(name: str) -> str:
    """Drop SNOMED semantic tags: 'Essential hypertension (disorder)' -> 'Essential hypertension'."""
    return TAG.sub("", name or "").strip()


def person_name(resource: dict) -> str:
    """Synthea appends digits to names to keep them unique: 'Aron520' -> 'Aron'."""
    n = (resource.get("name") or [{}])[0]
    parts = n.get("given", [])[:1] + [n.get("family", "")]
    return " ".join(re.sub(r"\d+", "", p) for p in parts if p).strip()


def utc(ts: str) -> str:
    """Sortable UTC timestamp from a FHIR dateTime ('2019-03-04T09:12:00-07:00' or '2019-03-04')."""
    if len(ts) == 10:
        return ts + "T00:00:00Z"
    return datetime.fromisoformat(ts).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def coding(concept: dict | None) -> tuple[str, str, str]:
    c = ((concept or {}).get("coding") or [{}])[0]
    system = c.get("system", "")
    short = "loinc" if "loinc" in system else "snomed" if "snomed" in system else "rxnorm" if "rxnorm" in system else "cvx" if "cvx" in system else system
    return short, c.get("code", ""), c.get("display") or (concept or {}).get("text", "")


UNITS = {"mm[Hg]": "mmHg", "Cel": "°C", "mL/min/{1.73_m2}": "mL/min/1.73m²", "{score}": "", "kg/m2": "kg/m²",
          "10*3/uL": "×10³/µL", "10*6/uL": "×10⁶/µL", "/min": "/min", "{nominal}": "", "[pH]": "", "pH": "",
          "{presence}": "", "{SG}": "", "{INR}": "", "{copies}/mL": "copies/mL", "m[IU]/L": "mIU/L", "/[HPF]": "/HPF"}


def _quantity(q: dict) -> tuple[float, str]:
    unit = q.get("unit") or q.get("code", "")
    return round(float(q["value"]), 2), UNITS.get(unit, unit)


def ingest_bundle(bundle: dict) -> tuple[dict, dict]:
    """Returns (chart, raw) where raw maps record id -> the original FHIR resource, trimmed."""
    entries = [e["resource"] for e in bundle["entry"]]
    meds = {r["id"]: r for r in entries if r["resourceType"] == "Medication"}
    patient = next(r for r in entries if r["resourceType"] == "Patient")
    records: list[dict] = []
    raw: dict[str, dict] = {}

    def add(rec: dict, resource: dict) -> None:
        records.append(rec)
        raw[rec["id"]] = trim(resource)

    for r in entries:
        t = r["resourceType"]
        if t == "Observation":
            cat = ((r.get("category") or [{}])[0].get("coding") or [{}])[0].get("code", "")
            system, code, display = coding(r.get("code"))
            if cat not in ("laboratory", "vital-signs") and code not in KEEP_SOCIAL_OBS:
                continue
            ts = r.get("effectiveDateTime")
            if not ts:
                continue
            rec = {"id": r["id"], "type": "Observation", "cat": "lab" if cat == "laboratory" else "vital" if cat == "vital-signs" else "social",
                   "system": system, "code": code, "name": display, "at": utc(ts), "date": ts[:10]}
            if "valueQuantity" in r:
                rec["value"], rec["unit"] = _quantity(r["valueQuantity"])
            elif "valueCodeableConcept" in r:
                rec["text"] = coding(r["valueCodeableConcept"])[2]
            elif "valueString" in r:
                rec["text"] = r["valueString"]
            elif "component" in r:
                parts = []
                for c in r["component"]:
                    if "valueQuantity" in c:
                        v, u = _quantity(c["valueQuantity"])
                        parts.append([coding(c.get("code"))[1], coding(c.get("code"))[2], v, u])
                if not parts:
                    continue
                rec["parts"] = parts
            else:
                continue
            add(rec, r)
        elif t == "Condition":
            system, code, display = coding(r.get("code"))
            if SOCIAL.search(display):
                continue
            onset = r.get("onsetDateTime") or r.get("recordedDate")
            status = ((r.get("clinicalStatus") or {}).get("coding") or [{}])[0].get("code", "active")
            rec = {"id": r["id"], "type": "Condition", "system": system, "code": code, "name": clean(display),
                   "at": utc(onset), "date": onset[:10], "status": status}
            if r.get("abatementDateTime"):
                rec["end"] = r["abatementDateTime"][:10]
            add(rec, r)
        elif t == "MedicationRequest":
            concept = r.get("medicationCodeableConcept")
            if concept is None and "medicationReference" in r:
                ref = r["medicationReference"]["reference"].split(":")[-1]
                concept = meds.get(ref, {}).get("code")
            system, code, display = coding(concept)
            ts = r["authoredOn"]
            rec = {"id": r["id"], "type": "MedicationRequest", "system": system, "code": code, "name": display,
                   "at": utc(ts), "date": ts[:10], "status": r.get("status", "")}
            reason = (r.get("reasonReference") or [{}])[0].get("display")
            if reason:
                rec["reason"] = clean(reason)
            add(rec, r)
        elif t == "AllergyIntolerance":
            system, code, display = coding(r.get("code"))
            ts = r.get("recordedDate") or r.get("onsetDateTime") or ""
            status = ((r.get("clinicalStatus") or {}).get("coding") or [{}])[0].get("code", "active")
            rec = {"id": r["id"], "type": "AllergyIntolerance", "system": system, "code": code, "name": clean(display),
                   "at": utc(ts) if ts else "", "date": ts[:10], "status": status,
                   "category": (r.get("category") or [""])[0], "criticality": r.get("criticality", "")}
            reactions = [clean(m.get("coding", [{}])[0].get("display", "")) for x in r.get("reaction", []) for m in x.get("manifestation", [])]
            if reactions:
                rec["reactions"] = reactions
            add(rec, r)
        elif t == "Immunization":
            system, code, display = coding(r.get("vaccineCode"))
            ts = r["occurrenceDateTime"]
            add({"id": r["id"], "type": "Immunization", "system": system, "code": code, "name": display,
                 "at": utc(ts), "date": ts[:10]}, r)
        elif t == "Encounter":
            system, code, display = coding((r.get("type") or [{}])[0])
            start = r["period"]["start"]
            rec = {"id": r["id"], "type": "Encounter", "system": system, "code": code, "name": clean(display),
                   "at": utc(start), "date": start[:10], "cls": r.get("class", {}).get("code", "")}
            reason = coding((r.get("reasonCode") or [None])[0])[2]
            if reason:
                rec["reason"] = clean(reason)
            add(rec, r)
        elif t == "Procedure":
            system, code, display = coding(r.get("code"))
            ts = r.get("performedDateTime") or (r.get("performedPeriod") or {}).get("start")
            if not ts:
                continue
            add({"id": r["id"], "type": "Procedure", "system": system, "code": code, "name": clean(display),
                 "at": utc(ts), "date": ts[:10]}, r)

    records.sort(key=lambda x: (x["at"], x["type"], x["code"], x["id"]))
    chart = {
        "id": patient["id"],
        "name": person_name(patient),
        "sex": patient.get("gender", ""),
        "birthDate": patient.get("birthDate", ""),
        "deceased": (patient.get("deceasedDateTime") or "")[:10] or None,
        "asOf": AS_OF,
        "records": records,
    }
    return chart, raw


def trim(resource: dict) -> dict:
    """The resource as a clinician or engineer would want to read it: no narrative HTML, no profile metadata."""
    out = {k: v for k, v in resource.items() if k not in ("text", "meta", "identifier", "participant", "location",
                                                          "serviceProvider", "requester", "performer", "presentedForm")}
    return out


def load_bundle(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
