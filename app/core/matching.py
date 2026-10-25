import csv
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from app.config import settings
from app.schemas import MatchedCaregiver, Location

_CAREGIVERS_CACHE: list[dict] = []

def load_caregivers() -> list[dict]:
    global _CAREGIVERS_CACHE
    if not _CAREGIVERS_CACHE:
        csv_path = settings.CAREGIVERS_CSV_FILE
        if not csv_path.exists():
            # Fallback to local official directory
            csv_path = Path(__file__).resolve().parent.parent.parent / "ml" / "data" / "official" / "caregivers.csv"

        if csv_path.exists():
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                records = []
                for row in reader:
                    records.append({
                        "caregiver_id": row["caregiver_id"],
                        "name": row["name"],
                        "role": row["role"],
                        "qualification": row.get("qualification", ""),
                        "gender": row.get("gender", ""),
                        "languages": [l.strip() for l in row["languages"].split(";") if l.strip()],
                        "skills": [s.strip() for s in row["skills"].split(";") if s.strip()],
                        "base_area": row.get("base_area", ""),
                        "base_lat": float(row["base_lat"]),
                        "base_lng": float(row["base_lng"]),
                        "max_radius_km": float(row["max_radius_km"]),
                        "tier": row.get("tier", "").strip() or "base",
                        "rating": float(row["rating"]) if row.get("rating") else 4.0,
                        "experience_years": int(row["experience_years"]) if row.get("experience_years") else 1,
                        "free_from": row.get("free_from", "09:00"),
                        "free_until": row.get("free_until", "18:00"),
                        "active": row.get("active", "True").strip().lower() in ["true", "1", "yes"],
                    })
                _CAREGIVERS_CACHE = records
    return _CAREGIVERS_CACHE


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


ROLE_MAPPING = {
    "paramedic_home_visit": "medic",
    "home_nursing": "medic",
    "lab_test_home": "phlebotomist",
    "teleconsultation": "doctor",
}

# Which synthetic venue may serve each care type. Hospital OPD rows never enter
# care-type matching (they stay in the secondary "other ways" list).
SYNTHETIC_VENUE_FOR_CARE_TYPE = {
    "paramedic_home_visit": "home",
    "home_nursing": "home",
    "teleconsultation": "virtual",
    "lab_test_home": None,
}

VENUE_LABELS = {"home": "home consult", "virtual": "video consult", "hospital": "OPD"}

# Localised fragments for the caregiver reason line, so the reason always
# follows the user's language (en / hi / hinglish).
_LANG_NAME = {
    "en": {"Hindi": "Hindi", "English": "English"},
    "hinglish": {"Hindi": "Hindi", "English": "English"},
    "hi": {"Hindi": "हिंदी", "English": "अंग्रेज़ी"},
}

_VENUE_LABELS_HI = {"home consult": "होम कंसल्ट", "video consult": "वीडियो परामर्श", "OPD": "ओपीडी"}

_DEPT_LABELS_HI = {
    "orthopaedics": "हड्डी रोग",
    "general medicine": "सामान्य चिकित्सा",
    "paediatrics": "बाल रोग",
    "gynaecology": "स्त्री रोग",
}


def _caregiver_reason(
    lang: str,
    *,
    primary_lang: str,
    care_type: str,
    is_synthetic: bool,
    dist_km: float,
    free_from: str,
    free_until: str,
    rating: float,
    venue_label: str = "",
    dept_label: str = "",
) -> str:
    """One readable reason line in the user's language (en/hi/hinglish)."""
    lang_key = lang if lang in ("hi", "hinglish") else "en"
    lang_name = _LANG_NAME[lang_key].get(primary_lang, primary_lang)

    if lang_key == "hi":
        v_label = _VENUE_LABELS_HI.get(venue_label, venue_label) if venue_label else ""
        d_label = _DEPT_LABELS_HI.get(dept_label, dept_label) if dept_label else ""
        if care_type == "teleconsultation":
            if is_synthetic:
                return f"{lang_name} बोलने वाले, {v_label}" + (f" · {d_label}" if d_label else "") + f", ★{rating}"
            return f"{lang_name} बोलने वाले, {free_from}–{free_until} उपलब्ध, ★{rating}"
        if is_synthetic:
            return f"{lang_name} बोलने वाले, {dist_km:.1f} किमी दूर, {v_label}" + (f" · {d_label}" if d_label else "") + f", {free_from}–{free_until} उपलब्ध"
        return f"{lang_name} बोलने वाले, {dist_km:.1f} किमी दूर, {free_from}–{free_until} उपलब्ध"

    if lang_key == "hinglish":
        if care_type == "teleconsultation":
            if is_synthetic:
                return f"{primary_lang} bolne wale, {venue_label}" + (f" · {dept_label}" if dept_label else "") + f", ★{rating}"
            return f"{primary_lang} bolne wale, {free_from}–{free_until} free, ★{rating}"
        if is_synthetic:
            return f"{primary_lang} bolne wale, {dist_km:.1f} km door, {venue_label}" + (f" · {dept_label}" if dept_label else "") + f", {free_from}–{free_until} free"
        return f"{primary_lang} bolne wale, {dist_km:.1f} km door, {free_from}–{free_until} free"

    # en
    if care_type == "teleconsultation":
        if is_synthetic:
            return f"{primary_lang}-speaking, {venue_label}" + (f" · {dept_label}" if dept_label else "") + f", ★{rating}"
        return f"{primary_lang}-speaking, free {free_from}–{free_until}, ★{rating}"
    if is_synthetic:
        return f"{primary_lang}-speaking, {dist_km:.1f} km away, {venue_label}" + (f" · {dept_label}" if dept_label else "") + f", free {free_from}–{free_until}"
    return f"{primary_lang}-speaking, {dist_km:.1f} km away, free {free_from}–{free_until}"


def _normalise_synthetic(row: dict) -> dict:
    """Synthetic rows use the official columns plus venue/facility/department.
    Normalised to the same dict shape as official caregivers so one ranking
    loop handles both. A radius of 0 means 'no radius stated' -> 15 km."""
    try:
        radius = float(row.get("max_radius_km") or 15.0)
        if radius <= 0:
            radius = 15.0
        return {
            "caregiver_id": row["caregiver_id"],
            "name": row.get("name", ""),
            "role": row.get("role") or "doctor",
            "qualification": row.get("qualification", ""),
            "gender": row.get("gender", ""),
            "languages": [l.strip() for l in (row.get("languages") or "").split(";") if l.strip()],
            "skills": [s.strip() for s in (row.get("skills") or "").split(";") if s.strip()],
            "base_area": row.get("base_area", ""),
            "base_lat": float(row.get("base_lat") or 28.54),
            "base_lng": float(row.get("base_lng") or 77.27),
            "max_radius_km": radius,
            "tier": row.get("tier", "").strip() or "base",
            "rating": float(row.get("rating") or 4.0),
            "experience_years": int(row.get("experience_years") or 1),
            "free_from": row.get("free_from", "09:00"),
            "free_until": row.get("free_until", "18:00"),
            "active": str(row.get("active", "True")).strip().lower() in ["true", "1", "yes"],
            "venue": row.get("venue", ""),
            "department": row.get("department", ""),
            "facility_name": row.get("facility_name", ""),
            "source": "synthetic",
        }
    except Exception:
        return None


def _synthetic_pool(care_type: str) -> list[dict]:
    """Synthetic doctors eligible for this care type (home-consult doctors for
    home visits, virtual doctors for teleconsultation). Empty when the flag is
    off or the care type has no synthetic venue."""
    if not settings.USE_SYNTHETIC_CAREGIVERS:
        return []
    venue = SYNTHETIC_VENUE_FOR_CARE_TYPE.get(care_type)
    if not venue:
        return []
    from app.core.synthetic import load_synthetic_caregivers
    out = []
    for row in load_synthetic_caregivers():
        if row.get("venue") != venue:
            continue
        norm = _normalise_synthetic(row)
        if norm:
            out.append(norm)
    return out


def window_open(free_from: str, free_until: str) -> bool:
    """True when the caregiver's window covers the current IST time."""
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    current = ist_now.strftime("%H:%M")
    return free_from <= current <= free_until


def rank_caregivers(
    care_type: str,
    urgency: str = "same_day",
    user_location: Location | None = None,
    user_language: str = "en",
    user_text: str = "",
    time_pref: str | None = None,
    limit: int = 3,
) -> list[MatchedCaregiver]:
    """
    Ranks official caregivers from ml/data/official/caregivers.csv according to:
    Score = 0.35*language + 0.30*proximity + 0.20*skill + 0.15*rating_normalised
    Emergency requests return empty list [].
    """
    if care_type == "emergency_112":
        return []

    target_role = ROLE_MAPPING.get(care_type)
    if not target_role:
        return []

    caregivers = load_caregivers()
    if settings.USE_SYNTHETIC_CAREGIVERS:
        caregivers = caregivers + _synthetic_pool(care_type)
    if not caregivers:
        return []

    u_lat = user_location.lat if user_location else 28.54
    u_lng = user_location.lng if user_location else 77.27

    lang_lower = (user_language or "en").lower()
    target_lang = "Hindi" if any(h in lang_lower for h in ["hi", "hinglish"]) else "English"

    # Current IST time for availability check
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    current_time_str = ist_now.strftime("%H:%M")

    # Detect nursing / procedure skills from user_text
    text_lower = user_text.lower() if user_text else ""
    detected_procedures = []
    procedure_map = {
        "injection_im": ["im injection", "injection im", "intramuscular"],
        "injection_iv": ["iv injection", "drip", "iv drip", "intravenous"],
        "wound_dressing": ["dressing", "wound", "patti", "bedsore", "bed sore", "zakham"],
        "catheter_care": ["catheter", "urine pipe", "urine bag"],
        "bp_sugar_check": ["bp", "sugar", "blood pressure", "glucose"],
        "vitals_monitoring": ["vitals", "temperature", "pulse", "oximeter"],
        "nebulization": ["nebulizer", "nebulization", "vapour"],
        "post_surgical_care": ["post surgical", "stitches", "surgery ke baad", "tanke"],
        "elderly_care": ["elderly", "old age", "bujurg", "dada", "dadi"],
        "sample_collection": ["sample", "blood test", "blood collection", "checkup"],
        "home_phlebotomy": ["phlebotomy", "blood sample", "blood test"],
    }
    for proc, keys in procedure_map.items():
        if any(k in text_lower for k in keys):
            detected_procedures.append(proc)

    candidates = []

    for cg in caregivers:
        is_synthetic = cg.get("source") == "synthetic"

        # 1. Role filter & Active status filter. Synthetic rows are doctors
        # allowed only for the venue mapped to the care type.
        if is_synthetic:
            if cg["role"] != "doctor":
                continue
            if cg.get("venue") != SYNTHETIC_VENUE_FOR_CARE_TYPE.get(care_type):
                continue
        else:
            if cg["role"] != target_role:
                continue
        if not cg["active"]:
            continue

        # 2. Distance filter
        dist_km = haversine_km(u_lat, u_lng, cg["base_lat"], cg["base_lng"])
        if care_type == "teleconsultation":
            proximity_score = 1.0
        else:
            if dist_km > cg["max_radius_km"]:
                continue
            proximity_score = max(0.0, min(1.0, 1.0 - (dist_km / cg["max_radius_km"])))

        # 3. Availability filter
        free_from = cg["free_from"]
        free_until = cg["free_until"]
        is_available = True
        if urgency == "same_day":
            # For same_day: require the window to include current time or start later today
            # If testing during off-hours, consider window open today
            if free_until < "06:00":
                is_available = False

        if not is_available:
            continue

        # 4. Language score (0.35)
        cg_langs = cg["languages"]
        if target_lang in cg_langs:
            lang_score = 1.0
            primary_lang = target_lang
        elif "English" in cg_langs:
            lang_score = 0.8
            primary_lang = "English"
        elif "Hindi" in cg_langs:
            lang_score = 0.8
            primary_lang = "Hindi"
        else:
            lang_score = 0.4
            primary_lang = cg_langs[0] if cg_langs else "Hindi"

        # 5. Skill score (0.20)
        cg_skills = cg["skills"]
        skill_score = 0.8

        if care_type == "home_nursing":
            if detected_procedures:
                matches = sum(1 for p in detected_procedures if p in cg_skills)
                skill_score = 1.0 if matches > 0 else 0.7
            else:
                skill_score = 0.9

            tier_bonuses = {"base": 0.0, "standard": 0.02, "advanced": 0.05, "expert": 0.08}
            skill_score = min(1.0, skill_score + tier_bonuses.get(cg["tier"], 0.0))

        elif care_type == "paramedic_home_visit":
            if is_synthetic:
                # Home-consult doctor: department fit drives the skill score.
                dept = cg.get("department", "")
                if dept == "orthopaedics":
                    skill_score = 0.9
                elif dept == "general_medicine":
                    skill_score = 0.8
                else:
                    skill_score = 0.7
            else:
                preferred = ["vitals_monitoring", "elderly_care", "nebulization"]
                matches = sum(1 for p in preferred if p in cg_skills)
                skill_score = min(1.0, 0.75 + 0.08 * matches)

        elif care_type == "lab_test_home":
            if any(s in cg_skills for s in ["sample_collection", "home_phlebotomy"]):
                skill_score = 1.0
            else:
                skill_score = 0.75

        elif care_type == "teleconsultation":
            skill_score = 1.0

        # 6. Rating normalized (0.15)
        rating_norm = float(cg["rating"]) / 5.0

        # Total weighted score
        final_score = round(
            0.35 * lang_score + 0.30 * proximity_score + 0.20 * skill_score + 0.15 * rating_norm,
            2,
        )

        # Build readable reason text in the user's language.
        if is_synthetic:
            venue_label = VENUE_LABELS.get(cg.get("venue"), cg.get("venue") or "consult")
            dept_label = (cg.get("department") or "").replace("_", " ")
        else:
            venue_label = ""
            dept_label = ""
        reason = _caregiver_reason(
            user_language,
            primary_lang=primary_lang,
            care_type=care_type,
            is_synthetic=is_synthetic,
            dist_km=dist_km,
            free_from=free_from,
            free_until=free_until,
            rating=float(cg["rating"]),
            venue_label=venue_label,
            dept_label=dept_label,
        )

        candidates.append({
            "caregiver_id": cg["caregiver_id"],
            "score": final_score,
            "reason": reason,
            "name": cg.get("name", ""),
            "role": cg.get("role", ""),
            "qualification": cg.get("qualification", ""),
            "languages": cg.get("languages", []),
            "rating": float(cg.get("rating", 4.0)),
            "free_from": free_from,
            "free_until": free_until,
            "distance_km": None if care_type == "teleconsultation" else round(dist_km, 1),
            "venue": cg.get("venue") if is_synthetic else None,
            "department": cg.get("department") if is_synthetic else None,
            "facility_name": cg.get("facility_name") if is_synthetic else None,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    return [
        MatchedCaregiver(
            caregiver_id=c["caregiver_id"],
            score=c["score"],
            reason=c["reason"],
            name=c.get("name"),
            role=c.get("role"),
            qualification=c.get("qualification"),
            languages=c.get("languages", []),
            rating=c.get("rating"),
            free_from=c.get("free_from"),
            free_until=c.get("free_until"),
            distance_km=c.get("distance_km"),
            venue=c.get("venue"),
            department=c.get("department"),
            facility_name=c.get("facility_name"),
        )
        for c in candidates[:limit]
    ]
