from app.config import settings
from app.schemas import PatientProfile


def bump_urgency(current_urgency: str, levels: int = 1) -> str:
    """
    Safely raise urgency by N levels (routine -> same_day -> immediate).
    Never lowers urgency.
    """
    order = settings.URGENCIES  # ["routine", "same_day", "immediate"]
    try:
        idx = order.index(current_urgency)
    except ValueError:
        idx = 0

    new_idx = min(len(order) - 1, idx + levels)
    return order[new_idx]


def apply_risk_modifiers(
    patient: PatientProfile | None,
    slots: dict,
    urgency: str,
    care_type: str,
) -> tuple[str, str, list[str]]:
    """
    Applies clinical risk modifiers. Only escalates urgency.
    Returns: (modified_urgency, modified_care_type, applied_modifiers)
    """
    applied = []
    final_urgency = urgency
    final_care_type = care_type

    symptoms = slots.get("symptoms", [])

    if not patient:
        # Check if age group was extracted in slots
        age_group = slots.get("age_group")
        if age_group == "senior" and ("fever" in symptoms or slots.get("breathing_difficulty")):
            final_urgency = bump_urgency(final_urgency, 1)
            applied.append("elderly_vulnerable_symptoms")
        return final_urgency, final_care_type, applied

    # 1. Age < 1 year or > 75 with fever or respiratory symptoms
    age = patient.age
    if age is not None:
        if (age < 1 or age > 75) and ("fever" in symptoms or slots.get("breathing_difficulty")):
            final_urgency = bump_urgency(final_urgency, 1)
            applied.append(f"age_{age}_with_symptoms")

    # 2. Pregnancy with bleeding or severe pain -> immediate emergency
    if patient.pregnant:
        if slots.get("bleeding") or "bleeding" in symptoms or "pain" in symptoms:
            final_urgency = "immediate"
            final_care_type = "emergency_referral"
            applied.append("pregnancy_acute_risk")

    # 3. Chronic conditions (diabetes, heart disease, copd, kidney) with fever / breathing
    chronic = [c.lower() for c in (patient.conditions or slots.get("chronic_conditions", []))]
    high_risk_conditions = {"diabetes", "heart disease", "copd", "kidney disease", "hypertension"}
    has_high_risk = any(cond in chronic for cond in high_risk_conditions)

    if has_high_risk and ("fever" in symptoms or slots.get("breathing_difficulty")):
        if final_urgency == "routine":
            final_urgency = bump_urgency(final_urgency, 1)
            applied.append("chronic_condition_with_acute_symptoms")

    # 4. Symptoms > 5 days -> at least same_day
    duration = slots.get("duration", "")
    if duration and (">5" in str(duration) or "5" in str(duration) or "week" in str(duration)):
        if final_urgency == "routine":
            final_urgency = "same_day"
            applied.append("prolonged_symptom_duration")

    return final_urgency, final_care_type, applied
