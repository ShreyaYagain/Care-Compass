def build_reasoning(
    symptoms: list[str],
    duration: str | None,
    breathing_difficulty: bool | None,
    chest_pain: bool | None,
    red_flags: list[str],
    care_type: str,
    urgency: str,
    modifiers: list[str],
    language: str = "en",
) -> str:
    """
    Constructs a plain-language explanation <= 2 sentences.
    Strictly avoids diagnosis, drug names, and doses.
    Uses official care_type and urgency enums.
    """
    # 1. Red flag / Emergency (emergency_112 / emergency)
    if red_flags or urgency == "emergency" or care_type == "emergency_112":
        if "chest_pain" in red_flags or chest_pain:
            return "Possible cardiac emergency requiring emergency services (112), not home care."
        if "breathlessness" in red_flags or breathing_difficulty:
            return "Severe shortness of breath requires immediate emergency services (112)."
        if "unconsciousness" in red_flags:
            return "Loss of consciousness requires immediate emergency services (112)."
        if "severe_bleeding" in red_flags:
            return "Severe uncontrolled bleeding requires immediate emergency medical services (112)."
        if red_flags:
            flags_readable = ", ".join(f.replace("_", " ") for f in red_flags[:2])
            return f"Red-flag symptoms detected ({flags_readable}); routed to emergency services (112), not home care."
        return "Critical symptoms detected; routed to emergency services (112), not home care."

    # 2. Symptom narrative
    sym_str = ", ".join(s.replace("_", " ") for s in symptoms) if symptoms else "Reported symptoms"
    dur_str = f" for {duration}" if duration else ""

    negations = []
    if breathing_difficulty is False:
        negations.append("no breathing difficulty reported")
    if chest_pain is False:
        negations.append("no chest pain reported")

    negation_str = f", {', '.join(negations)}" if negations else ""

    # 3. Action description by care_type
    care_action = {
        "paramedic_home_visit": "Medic home visit recommended for in-person assessment and vitals.",
        "home_nursing": "Specific nursing procedure requested; Medic home visit recommended.",
        "lab_test_home": "Home sample collection scheduled for diagnostic testing.",
        "teleconsultation": "Non-urgent query suitable for a virtual doctor consultation.",
    }.get(care_type, "Timely care is recommended.")

    modifier_note = ""
    if "chronic_condition_with_acute_symptoms" in modifiers:
        modifier_note = " Underlying conditions indicate same-day in-person monitoring."

    line1 = f"{sym_str.capitalize()}{dur_str}{negation_str}."
    return f"{line1} {care_action}{modifier_note}".strip()
