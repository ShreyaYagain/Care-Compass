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


def _window_open(free_from: str, free_until: str) -> bool:
    from datetime import datetime, timezone, timedelta
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    current = ist_now.strftime("%H:%M")
    return free_from <= current <= free_until


def home_consult_available(location=None, language: str = "", max_km: float = 15.0) -> bool:
    """True when at least one home-consult doctor (synthetic venue=home) is
    free right now, within max_km of the user, and speaks the language."""
    if not settings.USE_SYNTHETIC_CAREGIVERS:
        return False
    lang = _lang_hint(language)
    for row in load_synthetic_caregivers():
        if row.get("venue") != "home":
            continue
        if str(row.get("active", "True")).strip().lower() not in ("true", "1", "yes"):
            continue
        if not _window_open(row.get("free_from", "00:00"), row.get("free_until", "23:59")):
            continue
        if lang and lang not in (row.get("languages") or "").lower():
            continue
        if location and location.lat:
            dist = _dist_km(location.lat, location.lng, float(row.get("base_lat") or 0), float(row.get("base_lng") or 0))
            if dist > max_km:
                continue
        return True
    return False


def virtual_consult_available(language: str = "") -> bool:
    """True when at least one virtual doctor (synthetic venue=virtual) is free
    right now and speaks the language."""
    if not settings.USE_SYNTHETIC_CAREGIVERS:
        return False
    lang = _lang_hint(language)
    for row in load_synthetic_caregivers():
        if row.get("venue") != "virtual":
            continue
        if not _window_open(row.get("free_from", "00:00"), row.get("free_until", "23:59")):
            continue
        if lang and lang not in (row.get("languages") or "").lower():
            continue
        return True
    return False


def _dist_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def adjust_by_doctor_availability(care_type: str, urgency: str, location=None, language: str = "") -> tuple[str, str]:
    """Uses the synthetic doctor roster to refine a borderline routing choice.

    When a medic home visit was chosen but no home-consult doctor is free
    nearby while a virtual doctor IS free, offer teleconsultation instead.
    Never returns a new care_type; only swaps between the official two.
    Returns (care_type, reason_note)."""
    if not settings.USE_SYNTHETIC_CAREGIVERS:
        return care_type, ""
    if care_type == "paramedic_home_visit" and urgency == "same_day":
        if not home_consult_available(location, language) and virtual_consult_available(language):
            return "teleconsultation", (
                " No home-visit doctor is free right now, so we recommend an immediate "
                "video consultation; a home visit can be booked for the next available slot."
            )
    return care_type, ""
