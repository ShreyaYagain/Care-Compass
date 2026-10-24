from app.config import settings
from app.schemas import PatientProfile


def bump_urgency(current_urgency: str, levels: int = 1) -> str:
    """
    Safely raise urgency by at most 1 level.
    Total bump from all modifiers is at most +1 level, and only up to same_day.
    """
    if current_urgency == "scheduled":
        return "same_day"
    return current_urgency


def apply_risk_modifiers(
    patient: PatientProfile | None,
    slots: dict,
    urgency: str,
    care_type: str,
) -> tuple[str, str, list[str]]:
    """
    Applies clinical risk modifiers.
    Rule E: Total bump is at most +1 level, capped at same_day.
    Exception: pregnancy with acute severe pain/bleeding escalates to
    emergency_112 (deterministic safety rule).
    """
    applied = []
    final_urgency = urgency
    final_care_type = care_type

    symptoms = slots.get("symptoms", [])
    triggered = False

    # 3. Pregnancy (detected by the deterministic pregnancy layer or the profile):
    #    acute severe pain/bleeding -> emergency_112, otherwise a hard floor of
    #    same_day with teleconsultation at minimum (never "scheduled").
    is_pregnant = bool(slots.get("pregnancy") or (patient and patient.pregnant))
    if is_pregnant:
        if slots.get("bleeding") or "severe" in str(slots.get("severity")) or "acute" in str(slots.get("severity")):
            final_urgency = "emergency"
            final_care_type = "emergency_112"
            applied.append("pregnancy_acute_risk")
        else:
            if final_care_type == "lab_test_home":
                final_care_type = "teleconsultation"
            if final_urgency == "scheduled":
                final_urgency = "same_day"
            applied.append("pregnancy_min_same_day")

    if not patient:
        # Check if age group was extracted in slots
        age_group = slots.get("age_group")
        if age_group == "senior" and ("fever" in symptoms or slots.get("breathing_difficulty")):
            triggered = True
            applied.append("elderly_vulnerable_symptoms")
    else:
        # 1. Age < 1 year or > 75 with fever or respiratory symptoms
        age = patient.age
        if age is not None:
            if (age < 1 or age > 75) and ("fever" in symptoms or slots.get("breathing_difficulty")):
                triggered = True
                applied.append(f"age_{age}_with_symptoms")

        # 2. Chronic conditions with fever / breathing
        chronic = [c.lower() for c in (patient.conditions or slots.get("chronic_conditions", []))]
        high_risk_conditions = {"diabetes", "heart disease", "copd", "kidney disease", "hypertension"}
        has_high_risk = any(cond in chronic for cond in high_risk_conditions)

        if has_high_risk and ("fever" in symptoms or slots.get("breathing_difficulty")):
            triggered = True
            applied.append("chronic_condition_with_acute_symptoms")

    # 4. Symptoms > 5 days -> at least same_day
    duration = slots.get("duration", "")
    if duration and (">5" in str(duration) or "week" in str(duration)):
        triggered = True
        applied.append("prolonged_symptom_duration")

    # Raise scheduled -> same_day if clinical modifiers triggered
    if triggered and final_urgency == "scheduled":
        final_urgency = "same_day"

    return final_urgency, final_care_type, applied
