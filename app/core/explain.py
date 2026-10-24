import re
from app.core.guardrails import get_disclaimer, get_escalation_line, _load_guardrail_data, _LEXICON

# Human-readable symptom labels per language. Keys are the CANONICAL names in
# app/data/symptoms.yaml — never raw extracted tokens.
SYMPTOM_LABELS: dict[str, dict[str, str]] = {
    "fever": {"en": "fever", "hi": "बुखार", "hinglish": "bukhar"},
    "cough": {"en": "cough", "hi": "खांसी", "hinglish": "khansi"},
    "cold": {"en": "cold", "hi": "ज़ुकाम", "hinglish": "zukam"},
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


_BECAUSE_PREFIX = {
    "en": "Because you mentioned ",
    "hinglish": "Aapne bataya ",
    "hi": "आपने बताया ",
}

# Short duration suffixes per language (canonical slots only).
_DURATION_SUFFIX = {
    "en": {
        "today": "since morning", "1 day": "since yesterday", "2 days": "for 2 days",
        "3 days": "for 3 days", ">5 days": "for over 5 days",
        "More than a week": "for over a week",
    },
    "hinglish": {
        "today": "subah se", "1 day": "kal se", "2 days": "2 din se",
        "3 days": "3 din se", ">5 days": "5 din se zyada",
        "More than a week": "ek hafte se zyada",
    },
    "hi": {
        "today": "सुबह से", "1 day": "कल से", "2 days": "2 दिन से",
        "3 days": "3 दिन से", ">5 days": "5 दिन से अधिक",
        "More than a week": "एक हफ्ते से अधिक",
    },
}

# Short "next step" lines per care type per language (card only).
NEXT_LINES = {
    "paramedic_home_visit": {
        "en": "A medic will visit you at home today.",
        "hinglish": "Aaj hi medic ghar par aayega.",
        "hi": "आज ही मेडिक घर आएगा।",
    },
    "home_nursing": {
        "en": "A nurse will come home for your procedure.",
        "hinglish": "Nurse ghar aa kar procedure karegi.",
        "hi": "नर्स घर आकर प्रक्रिया करेगी।",
    },
    "lab_test_home": {
        "en": "We will collect your sample at home.",
        "hinglish": "Ghar par sample collection hoga.",
        "hi": "घर पर सैंपल कलेक्शन होगा।",
    },
    "teleconsultation": {
        "en": "Talk to a doctor today by video.",
        "hinglish": "Aaj hi video par doctor se baat karein.",
        "hi": "आज ही वीडियो पर डॉक्टर से बात करें।",
    },
    "emergency_112": {
        "en": "Call 112 now.",
        "hinglish": "Abhi 112 par call karein.",
        "hi": "अभी 112 पर कॉल करें।",
    },
}

# Mandatory safety line on every non-emergency card (guardrail requirement).
WATCH_FOR_LINES = {
    "en": "Call 112 if breathing trouble, chest pain, confusion or bleeding.",
    "hinglish": "Saans ki dikkat, seene mein dard, confusion ya bleeding ho to 112 call karein.",
    "hi": "सांस लेने में दिक्कत, सीने में दर्द, भ्रम या रक्तस्राव हो तो 112 पर कॉल करें।",
}

# Short "why" lines for emergency results.
EMERGENCY_WHY = {
    "chest_pain": {
        "en": "Chest pain can be a heart emergency.",
        "hinglish": "Seene mein dard heart emergency ho sakti hai.",
        "hi": "सीने का दर्द हृदय की आपातस्थिति हो सकती है।",
    },
    "breathlessness": {
        "en": "Breathing trouble can be dangerous.",
        "hinglish": "Saans ki dikkat khatarnak ho sakti hai.",
        "hi": "सांस लेने में दिक्कत खतरनाक हो सकती है।",
    },
    "unconsciousness": {
        "en": "Passing out is a serious sign.",
        "hinglish": "Behosh hona ek gambhir sanket hai.",
        "hi": "बेहोश होना गंभीर संकेत है।",
    },
    "severe_bleeding": {
        "en": "Heavy bleeding needs urgent care.",
        "hinglish": "Zyada bleeding me turant care chahiye.",
        "hi": "अधिक रक्तस्राव में तुरंत देखभाल चाहिए।",
    },
}

_NO_SYMPTOM_WHY = {
    "en": "Health concern noted.",
    "hinglish": "Health concern note kiya gaya.",
    "hi": "स्वास्थ्य संबंधी शिकायत दर्ज हुई।",
}

# Short context lines, shown ONLY when context changed the decision.
CONTEXT_LINES = {
    "night_rain": {
        "en": "Night time, so video consult first.",
        "hinglish": "Raat ka time hai, isliye pehle video consult.",
        "hi": "रात का समय है, इसलिए पहले वीडियो परामर्श।",
    },
    "heat_wave": {
        "en": "Heat wave with fever needs urgent care.",
        "hinglish": "Loo aur bukhar me turant care chahiye.",
        "hi": "लू और बुखार में तुरंत देखभाल चाहिए।",
    },
    "poor_air": {
        "en": "Hazardous air with asthma needs emergency care.",
        "hinglish": "Kharab hawa aur asthma me emergency care chahiye.",
        "hi": "खराब हवा और अस्थमा में आपात देखभाल चाहिए।",
    },
    "no_home_doctor": {
        "en": "No home-visit doctor free now, so video consult first.",
        "hinglish": "Abhi koi home-visit doctor free nahi hai, isliye video consult.",
        "hi": "अभी कोई होम-विज़िट डॉक्टर उपलब्ध नहीं है, इसलिए वीडियो परामर्श।",
    },
}


def context_line(context_key: str | None, language: str) -> str:
    """One short localized sentence for a context-driven decision change."""
    if not context_key:
        return ""
    lang = _lang(language)
    return (CONTEXT_LINES.get(context_key) or {}).get(lang, "")


def build_card_lines(
    care_type: str,
    urgency: str,
    symptoms: list[str],
    duration: str | None,
    red_flags: list[str],
    language: str = "en",
    context_key: str | None = None,
    chest_pain: bool | None = None,
    breathing_difficulty: bool | None = None,
    why_override: str | None = None,
) -> dict[str, str]:
    """Short card lines: why / next / watch_for / context_line, each 6-12
    words, one language only, no disclaimer, no weather/location."""
    lang = _lang(language)

    if care_type == "emergency_112" or urgency == "emergency":
        flag = ""
        if chest_pain or "chest_pain" in red_flags:
            flag = "chest_pain"
        elif breathing_difficulty or "breathlessness" in red_flags:
            flag = "breathlessness"
        elif "unconsciousness" in red_flags:
            flag = "unconsciousness"
        elif "severe_bleeding" in red_flags:
            flag = "severe_bleeding"
        why = why_override or (EMERGENCY_WHY.get(flag) or {}).get(lang, "") or _NO_SYMPTOM_WHY[lang]
        return {
            "why": why,
            "next": NEXT_LINES["emergency_112"][lang],
            "watch_for": "",
            "context_line": context_line(context_key, lang),
        }

    why = why_override
    if not why:
        labels = [_symptom_label(s, lang) for s in (symptoms or []) if s]
        if labels:
            joiner = {"en": " and ", "hinglish": " aur ", "hi": " और "}[lang]
            mention = joiner.join(labels[:3])
            dur = _DURATION_SUFFIX[lang].get(str(duration or ""), "")
            why = f"{mention} {dur}".strip()
            if lang != "hi":
                why = why[:1].upper() + why[1:]
        else:
            why = _NO_SYMPTOM_WHY[lang]
        why = why.rstrip(".") + "."

    next_line = NEXT_LINES.get(care_type, NEXT_LINES["teleconsultation"]).get(lang) or ""
    watch = WATCH_FOR_LINES[lang]
    return {
        "why": why,
        "next": next_line,
        "watch_for": watch,
        "context_line": context_line(context_key, lang),
    }


def card_text(lines: dict[str, str]) -> str:
    """The card joined as one short paragraph (no disclaimer, no weather)."""
    return " ".join(v for v in (lines.get("why"), lines.get("next"), lines.get("watch_for"), lines.get("context_line")) if v).strip()


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
    context_summary: str | None = None,
    top_terms: list[dict] | None = None,
    include_disclaimer: bool = True,
) -> str:
    """Short card paragraph (backward-compatible signature).

    - Canonical symptoms and validated slots only; raw classifier terms are
      never written.
    - The disclaimer paragraph is NOT part of the card (it lives in
      Settings/About and the first-run screen of the app).
    - Weather/location/AQI/season/time never appear in the card.
    - A context sentence appears only when context changed the decision.
    """
    lang = _lang(language)
    lines = build_card_lines(
        care_type=care_type,
        urgency=urgency,
        symptoms=symptoms,
        duration=duration,
        red_flags=red_flags,
        language=lang,
        chest_pain=chest_pain,
        breathing_difficulty=breathing_difficulty,
    )
    if context_reason and context_reason in CONTEXT_LINES:
        lines["context_line"] = context_line(context_reason, lang)
    return card_text(lines)
