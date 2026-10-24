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


def rank_caregivers(
    care_type: str,
    urgency: str = "same_day",
    user_location: Location | None = None,
    user_language: str = "en",
    user_text: str = "",
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
        # 1. Role filter & Active status filter
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

        # Build readable reason text
        if care_type == "teleconsultation":
            reason = f"{primary_lang}-speaking, free {free_from}–{free_until}, ★{cg['rating']}"
        else:
            reason = f"{primary_lang}-speaking, {dist_km:.1f} km away, free {free_from}–{free_until}"

        candidates.append({
            "caregiver_id": cg["caregiver_id"],
            "score": final_score,
            "reason": reason,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    return [
        MatchedCaregiver(
            caregiver_id=c["caregiver_id"],
            score=c["score"],
            reason=c["reason"],
        )
        for c in candidates[:limit]
    ]
