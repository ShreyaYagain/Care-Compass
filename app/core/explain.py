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
    Constructs a plain-language clinical explanation <= 2 sentences.
    Strictly avoids diagnosis, drug names, and doses.
    """
    # 1. Red flag / Emergency
    if red_flags or urgency == "immediate":
        if "chest_pain" in red_flags or chest_pain:
            return "Chest pain with difficulty breathing needs emergency care now."
        if "severe_breathlessness" in red_flags or breathing_difficulty:
            return "Severe shortness of breath requires immediate emergency hospital evaluation."
        if "unconsciousness" in red_flags:
            return "Loss of consciousness requires immediate emergency medical attention."
        if red_flags:
            flags_readable = ", ".join(f.replace("_", " ") for f in red_flags[:2])
            return f"Critical signs ({flags_readable}) detected requiring immediate emergency intervention."
        return "Immediate medical evaluation is required at the nearest emergency facility."

    # 2. Symptom narrative
    sym_str = ", ".join(s.replace("_", " ") for s in symptoms) if symptoms else "Reported symptoms"
    dur_str = f" for {duration}" if duration else ""

    negations = []
    if breathing_difficulty is False:
        negations.append("no breathing difficulty reported")
    if chest_pain is False:
        negations.append("no chest pain reported")

    negation_str = f", {', '.join(negations)}" if negations else ""

    # 3. Risk modifier notes
    modifier_note = ""
    if "age_with_symptoms" in str(modifiers) or any("age_" in m for m in modifiers):
        modifier_note = " Age-based monitoring prompted same-day assessment."
    elif "chronic_condition_with_acute_symptoms" in modifiers:
        modifier_note = " Underlying health conditions indicate same-day in-person monitoring."

    # Example: "Fever with cough for 2 days, no breathing difficulty reported. Recommended for same-day home visit."
    care_action = {
        "paramedic_home_visit": "A paramedic home visit is recommended to check vital signs.",
        "nurse_home_visit": "A nurse home visit is recommended for dressing and in-person care.",
        "gp_teleconsult": "A general doctor consultation is recommended to review symptoms.",
        "specialist": "A specialist consultation is recommended for targeted evaluation.",
    }.get(care_type, "Timely medical care is recommended.")

    line1 = f"{sym_str.capitalize()}{dur_str}{negation_str}."
    return f"{line1} {care_action}{modifier_note}".strip()
