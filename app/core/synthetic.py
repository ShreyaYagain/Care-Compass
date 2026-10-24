"""Synthetic caregivers (demo "Other ways to see a doctor" list).

Separate from the official `ml/data/official/caregivers.csv`. These rows add
`venue` (hospital | home | virtual), `facility_name`, `department` and
`source=synthetic`. They never produce a new care_type and are labelled demo
data in the app. Gated behind settings.USE_SYNTHETIC_CAREGIVERS.
"""
from __future__ import annotations

import csv
from typing import Optional

from app.config import settings

_CACHE: list[dict] = []


def load_synthetic_caregivers() -> list[dict]:
    global _CACHE
    if not _CACHE and settings.SYNTHETIC_CAREGIVERS_FILE.exists():
        try:
            with open(settings.SYNTHETIC_CAREGIVERS_FILE, "r", encoding="utf-8") as f:
                _CACHE = [dict(r) for r in csv.DictReader(f)]
        except Exception:
            _CACHE = []
    return _CACHE


def synthetic_caregivers(
    department: Optional[str] = None,
    venue: Optional[str] = None,
    language: Optional[str] = None,
) -> list[dict]:
    if not settings.USE_SYNTHETIC_CAREGIVERS:
        return []
    out = load_synthetic_caregivers()
    if venue:
        out = [c for c in out if c.get("venue") == venue]
    if department:
        out = [c for c in out if c.get("department") == department]
    if language:
        out = [c for c in out if language.lower() in (c.get("languages") or "").lower()]
    return out


def secondary_doctor_options(care_type: str, language: str) -> list[dict]:
    """The demo 'Other ways to see a doctor' list for a triage result."""
    if not settings.USE_SYNTHETIC_CAREGIVERS:
        return []
    all_docs = load_synthetic_caregivers()

    # Relevant departments for the care type (general medicine always included).
    dept = _dept_for(care_type)
    lang = _lang_hint(language)

    picks = []
    for c in all_docs:
        if c.get("role") != "doctor":
            continue
        # Prefer department match; keep general medicine as a fallback pool.
        if dept and c.get("department") != dept and c.get("department") != "general_medicine":
            continue
        if lang and lang not in (c.get("languages") or "").lower():
            continue
        picks.append(c)

    # De-duplicate by id and return up to 6, labelled demo data.
    seen = set()
    out = []
    for c in sorted(picks, key=lambda x: -float(x.get("rating") or 0)):
        if c["caregiver_id"] in seen:
            continue
        seen.add(c["caregiver_id"])
        out.append({
            "caregiver_id": c["caregiver_id"],
            "name": c["name"],
            "qualification": c.get("qualification", ""),
            "venue": c.get("venue"),
            "facility_name": c.get("facility_name") or None,
            "department": c.get("department"),
            "rating": float(c.get("rating") or 0),
            "languages": (c.get("languages") or "").split(";"),
            "demo": True,
        })
        if len(out) >= 6:
            break
    return out


def _dept_for(care_type: str) -> Optional[str]:
    return {
        "paramedic_home_visit": "orthopaedics",
        "home_nursing": "general_medicine",
        "teleconsultation": "general_medicine",
        "lab_test_home": None,
    }.get(care_type)


def _lang_hint(language: str) -> str:
    if not language or language == "auto":
        return ""
    if "hi" in language.lower() or "hinglish" in language.lower():
        return "hindi"
    return "english"
