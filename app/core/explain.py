import re
from app.core.guardrails import get_disclaimer, get_escalation_line, _load_guardrail_data, _LEXICON

# Human-readable symptom labels per language. Keys are the CANONICAL names in
# app/data/symptoms.yaml — never raw extracted tokens.
SYMPTOM_LABELS: dict[str, dict[str, str]] = {
    "fever": {"en": "fever", "hi": "बुखार", "hinglish": "bukhar"},
    "cough": {"en": "cough", "hi": "खांसी", "hinglish": "khansi"},
    "chest_pain": {"en": "chest pain", "hi": "सीने में दर्द", "hinglish": "seene mein dard"},
    "breathlessness": {"en": "breathlessness", "hi": "सांस फूलना", "hinglish": "saans phoolna"},
    "stomach_pain": {"en": "stomach pain", "hi": "पेट दर्द", "hinglish": "pet dard"},
    "injury": {"en": "injury", "hi": "चोट", "hinglish": "chot"},
    "vomiting": {"en": "vomiting", "hi": "उल्टी", "hinglish": "ulti"},
    "headache": {"en": "headache", "hi": "सिर दर्द", "hinglish": "sir dard"},
    "joint_pain": {"en": "joint pain", "hi": "जोड़ों का दर्द", "hinglish": "jodo ka dard"},
    "restlessness": {"en": "restlessness", "hi": "बेचैनी", "hinglish": "bechaini"},
    "dizziness": {"en": "dizziness", "hi": "चक्कर आना", "hinglish": "chakkar aana"},
    "weakness": {"en": "weakness", "hi": "कमजोरी", "hinglish": "kamzori"},
    "nursing_procedure": {"en": "nursing procedure", "hi": "नर्सिंग प्रक्रिया", "hinglish": "nursing procedure"},
    "lab_test": {"en": "lab test", "hi": "लैब टेस्ट", "hinglish": "lab test"},
    "teleconsultation_query": {"en": "consultation request", "hi": "परामर्श", "hinglish": "consultation"},
}

# Full action sentences per care type per language.
CARE_ACTION: dict[str, dict[str, str]] = {
    "paramedic_home_visit": {
        "en": "A medic home visit is recommended for in-person assessment and vitals.",
        "hinglish": "Ghar par medic visit recommended hai jaanch aur vitals ke liye.",
        "hi": "घर पर मेडिक विज़िट की सिफारिश की जाती है।",
    },
    "home_nursing": {
        "en": "A home nursing procedure is recommended.",
        "hinglish": "Home nursing procedure recommended hai.",
        "hi": "होम नर्सिंग प्रक्रिया की सिफारिश की जाती है।",
    },
    "lab_test_home": {
        "en": "Home sample collection is scheduled for diagnostic testing.",
        "hinglish": "Ghar par sample collection diagnostic test ke liye scheduled hai.",
        "hi": "घर पर सैंपल कलेक्शन निर्धारित है।",
    },
    "teleconsultation": {
        "en": "A virtual doctor consultation is recommended.",
        "hinglish": "Video par doctor consultation recommended hai.",
        "hi": "वीडियो डॉक्टर परामर्श की सिफारिश की जाती है।",
    },
}

_BECAUSE_PREFIX = {
    "en": "Because you mentioned ",
    "hinglish": "Aapne bataya ",
    "hi": "आपने बताया ",
}


def _lang(language: str | None) -> str:
    return language if language in ("en", "hi", "hinglish") else "en"


def _symptom_label(name: str, language: str) -> str:
    labels = SYMPTOM_LABELS.get(name)
    if labels:
        return labels.get(language) or labels["en"]
    return name.replace("_", " ")


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
    - Symptom names come ONLY from the canonical lexicon (symptoms.yaml) and are
      shown in the user's language.
    - Raw classifier n-gram terms ("tin", "ting") are never written.
    - If no valid symptom was recognised, no "Because you mentioned ..."
      sentence is produced.
    - Never names a disease, medicine, or gives false reassurance.
    - Disclaimer ("not a doctor") appears once, in the user's language.
    """
    _load_guardrail_data()
    lang = _lang(language)
    disclaimer = get_disclaimer(lang) if include_disclaimer else ""

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

    # 2. Canonical symptoms only (never raw classifier terms). `top_terms` is
    # accepted for backward compatibility but deliberately ignored: TF-IDF char
    # n-grams are not symptom names.
    mention = ""
    labels = [_symptom_label(s, lang) for s in symptoms if s]
    if labels:
        mention = _BECAUSE_PREFIX[lang] + " aur ".join(labels[:3]) if lang != "en" else _BECAUSE_PREFIX[lang] + " and ".join(labels[:3])

    if duration:
        dur_label = {
            "en": f" for {duration}",
            "hinglish": f" {duration} se",
            "hi": f" {duration} से",
        }[lang]
        mention = f"{mention}{dur_label}"

    negations = []
    if breathing_difficulty is False:
        negations.append({
            "en": "no breathing difficulty reported",
            "hinglish": "saans me koi dikkat nahi batayi gayi",
            "hi": "सांस लेने में कोई दिक्कत नहीं बताई गई",
        }[lang])
    if chest_pain is False:
        negations.append({
            "en": "no chest pain reported",
            "hinglish": "seene me koi dard nahi bataya gaya",
            "hi": "सीने में कोई दर्द नहीं बताया गया",
        }[lang])

    action = CARE_ACTION.get(care_type, {}).get(lang) or CARE_ACTION.get(care_type, {}).get("en", "Timely care is recommended.")

    # Without any recognised symptom, never claim the user mentioned something.
    if mention:
        res = f"{mention}. {action}"
    else:
        res = action

    if negations:
        res = f"{res} {', '.join(negations)}."

    modifier_note = ""
    if "chronic_condition_with_acute_symptoms" in modifiers:
        modifier_note = {
            "en": " Underlying conditions indicate same-day in-person monitoring.",
            "hinglish": " Underlying conditions ki wajah se same-day monitoring zaroori hai.",
            "hi": " पुरानी बीमारियों के कारण उसी दिन निगरानी आवश्यक है।",
        }[lang]
        res = f"{res}{modifier_note}"

    if context_reason:
        res = f"{res} {context_reason}".strip()

    # 3. Mandatory escalation line on non-emergency answers
    escalation = get_escalation_line(lang)

    parts = []
    if disclaimer:
        parts.append(disclaimer)
    parts.append(res)
    parts.append(escalation)

    return " ".join(parts).strip()
