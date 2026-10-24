import re
from app.core.guardrails import get_disclaimer, get_escalation_line, _load_guardrail_data, _LEXICON


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
    context_reason: str | None = None,
    top_terms: list[dict] | None = None,
    include_disclaimer: bool = True,
) -> str:
    """
    Constructs a plain-language explanation adhering to the Response Policy:
    - Never names a disease or likely condition.
    - Never mentions medicine names, doses, or home-remedy dosages.
    - Never gives false reassurance.
    - Never discourages seeking care or calling 112.
    - Always includes escalation line on non-emergency answers in user's language.
    - Plain words (approx Grade 6 reading level), max 2 sentences for core rationale.
    - Shows disclaimer once per session (if include_disclaimer=True).
    """
    _load_guardrail_data()
    disclaimer = get_disclaimer(language) if include_disclaimer else ""

    # 1. Red flag / Emergency (emergency_112 / emergency)
    if red_flags or urgency == "emergency" or care_type == "emergency_112":
        prefix = ""
        if context_reason:
            prefix = f"{context_reason} "
        if "chest_pain" in red_flags or chest_pain:
            base = "Possible cardiac emergency requiring emergency services (112), not home care."
        elif "breathlessness" in red_flags or breathing_difficulty:
            base = "Severe shortness of breath requires immediate emergency services (112)."
        elif "unconsciousness" in red_flags:
            base = "Loss of consciousness requires immediate emergency services (112)."
        elif "severe_bleeding" in red_flags:
            base = "Severe uncontrolled bleeding requires immediate emergency medical services (112)."
        elif red_flags:
            flags_readable = ", ".join(f.replace("_", " ") for f in red_flags[:2])
            base = f"Red-flag symptoms detected ({flags_readable}); routed to emergency services (112), not home care."
        else:
            base = "Critical symptoms detected; routed to emergency services (112), not home care."

        full_emergency = f"{prefix}{base}".strip()
        if disclaimer:
            return f"{disclaimer} {full_emergency}".strip()
        return full_emergency

    # 2. Symptom narrative & top contributing clean terms
    terms_phrase = ""
    if top_terms:
        clean_terms = []
        diseases = _LEXICON.get("diseases", [])
        drugs = _LEXICON.get("drugs_and_medicines", [])
        for item in top_terms[:3]:
            t = item.get("term", "").strip().lower()
            if len(t) >= 3 and t not in clean_terms:
                # Do not leak diseases or drug names into explanation
                if any(dis == t for dis in diseases) or any(drug == t for drug in drugs):
                    continue
                clean_terms.append(t)
        if clean_terms:
            terms_phrase = f"Because you mentioned {' and '.join(clean_terms[:2])}, "

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
        "home_nursing": "home nursing procedure recommended.",
        "lab_test_home": "home sample collection scheduled for diagnostic testing.",
        "teleconsultation": "virtual doctor consultation recommended.",
    }.get(care_type, "Timely care is recommended.")

    modifier_note = ""
    if "chronic_condition_with_acute_symptoms" in modifiers:
        modifier_note = " Underlying conditions indicate same-day in-person monitoring."

    if terms_phrase and care_type in ["home_nursing", "lab_test_home", "teleconsultation"]:
        res = f"{terms_phrase}we suggest {care_action}{modifier_note}".strip()
    else:
        line1 = f"{sym_str.capitalize()}{dur_str}{negation_str}."
        res = f"{line1} {care_action}{modifier_note}".strip()

    if context_reason:
        res = f"{res} {context_reason}".strip()

    # 4. Mandatory escalation line on non-emergency answers
    escalation = get_escalation_line(language)

    parts = []
    if disclaimer:
        parts.append(disclaimer)
    parts.append(res)
    parts.append(escalation)

    return " ".join(parts).strip()
