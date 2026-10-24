import json
import math
from pathlib import Path
from app.config import settings
from app.schemas import CaregiverProfile, MatchedCaregiver, Location

_CAREGIVERS_CACHE: list[CaregiverProfile] = []


def load_caregivers() -> list[CaregiverProfile]:
    global _CAREGIVERS_CACHE
    if not _CAREGIVERS_CACHE and settings.CAREGIVERS_FILE.exists():
        try:
            with open(settings.CAREGIVERS_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                _CAREGIVERS_CACHE = [CaregiverProfile(**cg) for cg in raw_data]
        except Exception:
            _CAREGIVERS_CACHE = []
    return _CAREGIVERS_CACHE


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371.0  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


ROLE_MAPPING = {
    "paramedic_home_visit": ["paramedic", "nurse"],
    "nurse_home_visit": ["nurse"],
    "gp_teleconsult": ["gp"],
    "specialist": ["specialist", "gp"],
    "emergency_referral": ["paramedic"],
}


def rank_caregivers(
    care_type: str,
    urgency: str,
    user_location: Location | None = None,
    user_language: str = "auto",
    time_pref: str | None = None,
    limit: int = 3,
) -> list[MatchedCaregiver]:
    """
    Ranks caregivers using the multi-factor scoring formula defined in BACKEND_SPEC.md.
    """
    caregivers = load_caregivers()
    if not caregivers:
        return []

    # Fallback coordinates (Central/South Delhi) if user_location not provided
    u_lat = user_location.lat if user_location else 28.54
    u_lng = user_location.lng if user_location else 77.27

    weights = settings.MATCHING_WEIGHTS.get(urgency, settings.MATCHING_WEIGHTS["routine"])
    allowed_roles = ROLE_MAPPING.get(care_type, ["paramedic", "nurse", "gp", "specialist"])
    needs_home_visit = "home_visit" in care_type or care_type == "paramedic_home_visit"

    scored_caregivers = []

    for cg in caregivers:
        # Step 1: Hard filters
        if cg.role not in allowed_roles:
            continue
        if needs_home_visit and not cg.home_visit:
            continue
        if not cg.availability_slots:
            continue

        dist_km = haversine_km(u_lat, u_lng, cg.lat, cg.lng)
        if dist_km > settings.MAX_KM:
            continue

        # Step 2: Feature scores [0, 1]
        # 1. Skill match
        if care_type == "paramedic_home_visit":
            skill_score = 1.0 if cg.role == "paramedic" else 0.7
        elif care_type == "nurse_home_visit":
            skill_score = 1.0 if cg.role == "nurse" else 0.6
        elif care_type == "gp_teleconsult":
            skill_score = 1.0 if cg.role == "gp" else 0.7
        elif care_type == "specialist":
            skill_score = 1.0 if cg.role == "specialist" else 0.6
        else:
            skill_score = 0.8

        # 2. Distance score: exp(-km / 5.0)
        distance_score = math.exp(-dist_km / 5.0)

        # 3. Availability score
        avail_score = 0.5
        earliest_slot = cg.availability_slots[0]
        if "immediate" in earliest_slot:
            avail_score = 1.0
        elif "today" in earliest_slot or "afternoon" in earliest_slot or "evening" in earliest_slot:
            avail_score = 0.8 if urgency == "same_day" else 0.9
        elif "tomorrow" in earliest_slot:
            avail_score = 0.4 if urgency == "same_day" else 0.8

        # 4. Language score
        lang_score = 0.5
        norm_user_lang = "hi" if user_language in ["hi", "hinglish", "auto"] else user_language
        if norm_user_lang in cg.languages or "hinglish" in cg.languages:
            lang_score = 1.0
        elif "en" in cg.languages:
            lang_score = 0.7
        else:
            lang_score = 0.2

        # 5. Rating score (shrink toward mean)
        rating_score = max(0.0, min(1.0, (cg.rating - 1.0) / 4.0))

        # Step 3: Weighted sum
        total_score = (
            weights["skill"] * skill_score
            + weights["distance"] * distance_score
            + weights["availability"] * avail_score
            + weights["language"] * lang_score
            + weights["rating"] * rating_score
        )

        factors = {
            "skill": round(skill_score, 2),
            "distance": round(distance_score, 2),
            "availability": round(avail_score, 2),
            "language": round(lang_score, 2),
            "rating": round(rating_score, 2),
        }

        # Step 5: Factual reason string
        reason_parts = []
        if "hi" in cg.languages:
            reason_parts.append("Hindi-speaking")
        elif "en" in cg.languages:
            reason_parts.append("English-speaking")

        dist_str = f"{dist_km:.1f} km away" if dist_km >= 1.0 else f"{int(dist_km * 1000)} m away"
        reason_parts.append(dist_str)

        if "immediate" in earliest_slot:
            reason_parts.append("available immediately")
        elif "afternoon" in earliest_slot:
            reason_parts.append("available this afternoon")
        elif "evening" in earliest_slot:
            reason_parts.append("free this evening")
        else:
            reason_parts.append("slot available tomorrow")

        reason = ", ".join(reason_parts)

        scored_caregivers.append(
            (total_score, dist_km, MatchedCaregiver(
                caregiver_id=cg.id,
                score=round(total_score, 2),
                reason=reason,
                factors=factors,
            ))
        )

    # Sort descending by score, tie-break by distance ascending
    scored_caregivers.sort(key=lambda x: (-x[0], x[1]))
    return [item[2] for item in scored_caregivers[:limit]]
