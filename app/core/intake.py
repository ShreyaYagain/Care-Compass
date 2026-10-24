import re
import yaml
from pathlib import Path
from app.config import settings
from app.core.language import normalise_text, is_phrase_negated
from app.core.llm import call_gemini_json, is_llm_available

_SYMPTOMS_CONFIG: dict = {}


def _load_symptoms_config():
    global _SYMPTOMS_CONFIG
    if not _SYMPTOMS_CONFIG and settings.SYMPTOMS_FILE.exists():
        try:
            with open(settings.SYMPTOMS_FILE, "r", encoding="utf-8") as f:
                _SYMPTOMS_CONFIG = yaml.safe_load(f) or {}
        except Exception:
            _SYMPTOMS_CONFIG = {}


def default_slots() -> dict:
    return {
        "symptoms": [],
        "duration": None,
        "severity": None,
        "age_group": None,
        "patient_relation": "self",
        "breathing_difficulty": None,
        "chest_pain": None,
        "consciousness": "alert",
        "bleeding": None,
        "fever_temp": None,
        "pregnancy": False,
        "chronic_conditions": [],
    }


def rule_based_extract(text: str, history: list[dict] = None) -> dict:
    """
    Deterministic rule/regex slot extraction fallback.
    """
    _load_symptoms_config()
    slots = default_slots()

    # Combine current text with conversation history
    full_conversation = text
    if history:
        for msg in history:
            full_conversation += " " + (msg.get("text") or "")

    norm = normalise_text(full_conversation)

    # 1. Relation detection
    relations = {
        "papa": "father", "pitaji": "father", "father": "father",
        "mummy": "mother", "mataji": "mother", "maa": "mother", "mother": "mother",
        "dadi": "grandmother", "nani": "grandmother", "dada": "grandfather",
        "bachha": "child", "beta": "child", "beti": "child", "baby": "child",
        "patni": "wife", "wife": "wife", "pati": "husband", "husband": "husband"
    }
    for word, rel in relations.items():
        if re.search(rf"\b{word}\b", norm):
            slots["patient_relation"] = rel
            break

    # 2. Symptom discovery
    symptoms_list = _SYMPTOMS_CONFIG.get("symptoms_list", {})
    detected_symptoms = []
    for sym_name, sym_info in symptoms_list.items():
        syns = sym_info.get("synonyms", [])
        for syn in syns:
            syn_norm = normalise_text(syn)
            if syn_norm in norm:
                # Check negation
                if is_phrase_negated(syn, full_conversation):
                    if sym_name == "breathlessness":
                        slots["breathing_difficulty"] = False
                    elif sym_name == "chest_pain":
                        slots["chest_pain"] = False
                else:
                    if sym_name not in detected_symptoms:
                        detected_symptoms.append(sym_name)
                    if sym_name == "breathlessness":
                        slots["breathing_difficulty"] = True
                    elif sym_name == "chest_pain":
                        slots["chest_pain"] = True
                break

    slots["symptoms"] = detected_symptoms

    # 3. Direct checks for breathing & chest pain if not explicitly set
    if slots["breathing_difficulty"] is None:
        if any(w in norm for w in ["breathing", "saans", "sans"]):
            if is_phrase_negated("saans", full_conversation) or is_phrase_negated("breathing", full_conversation):
                slots["breathing_difficulty"] = False
            elif any(w in norm for w in ["dikkat", "takleef", "difficulty", "shortness"]):
                slots["breathing_difficulty"] = True

    if slots["chest_pain"] is None:
        if any(w in norm for w in ["chest pain", "seene me dard"]):
            if is_phrase_negated("chest pain", full_conversation) or is_phrase_negated("seene me dard", full_conversation):
                slots["chest_pain"] = False
            else:
                slots["chest_pain"] = True

    # 4. Duration
    if any(p in norm for p in ["do din", "2 din", "2 days", "two days"]):
        slots["duration"] = "2 days"
    elif any(p in norm for p in ["ek din", "1 din", "1 day", "one day", "kal se"]):
        slots["duration"] = "1 day"
    elif any(p in norm for p in ["aaj se", "today", "subah se"]):
        slots["duration"] = "today"
    elif any(p in norm for p in ["hafta", "week", "5 din", "5 days"]):
        slots["duration"] = ">5 days"

    # 5. Chronic conditions
    conditions = []
    if "diabetes" in norm or "sugar" in norm:
        conditions.append("diabetes")
    if "hypertension" in norm or "high bp" in norm or "bp" in norm:
        conditions.append("hypertension")
    if "asthma" in norm or "dama" in norm:
        conditions.append("asthma")
    slots["chronic_conditions"] = conditions

    # 6. Age group
    if slots["patient_relation"] in ["child", "baby"]:
        slots["age_group"] = "child"
    elif slots["patient_relation"] in ["grandmother", "grandfather"]:
        slots["age_group"] = "senior"

    return slots


def extract_slots(text: str, history: list[dict] = None) -> dict:
    """
    Extracts structured slots via Gemini if available, else falls back to rule_based_extract.
    """
    if is_llm_available():
        prompt = f"""Extract healthcare triage slots from this patient conversation.
Conversation history: {history or []}
Current message: "{text}"

Return JSON matching this exact structure:
{{
  "symptoms": ["list of detected symptoms e.g. fever, cough, chest_pain, breathlessness"],
  "duration": "duration if mentioned e.g. 2 days or null",
  "severity": "mild, moderate, or severe or null",
  "age_group": "child, adult, senior or null",
  "patient_relation": "father, mother, child, self, etc.",
  "breathing_difficulty": true/false/null,
  "chest_pain": true/false/null,
  "consciousness": "alert, drowsy, or unconscious",
  "bleeding": true/false/null,
  "fever_temp": "e.g. 102F or null",
  "pregnancy": true/false/null,
  "chronic_conditions": ["e.g. diabetes, hypertension"]
}}"""
        llm_res = call_gemini_json(prompt, system_instruction="You are a medical intake assistant. Output valid JSON only.")
        if llm_res and isinstance(llm_res, dict) and "symptoms" in llm_res:
            return llm_res

    return rule_based_extract(text, history)


def needs_more_info(slots: dict, history_turns: int) -> bool:
    """
    Check if we need to ask follow-up questions.
    Max 4 turns. Prefer 2.
    Ask if safety-critical slots are unknown when related symptoms (fever, cough, chest, weakness) exist.
    """
    if history_turns >= settings.MAX_FOLLOWUPS:
        return False

    symptoms = slots.get("symptoms", [])

    # If nothing has been extracted at all, we definitely need more info
    if not symptoms and not slots.get("duration"):
        return True

    # If patient has respiratory or chest symptoms but breathing_difficulty is not known
    if any(s in symptoms for s in ["fever", "cough", "breathlessness"]) and slots.get("breathing_difficulty") is None:
        if history_turns < 2:
            return True

    # If patient has chest discomfort or pain, but chest_pain clarity is not known
    if "chest_pain" in symptoms and slots.get("chest_pain") is None:
        return True

    # If patient is elderly or child with fever and duration is unknown
    if "fever" in symptoms and slots.get("duration") is None and history_turns == 0:
        return True

    return False


def select_follow_up_question(slots: dict, lang: str = "en") -> tuple[str, list[str]]:
    """
    Select follow-up question based on safety priority from symptoms.yaml.
    """
    _load_symptoms_config()
    slots_config = _SYMPTOMS_CONFIG.get("slots", {})

    target_lang = "hinglish" if lang in ["hinglish", "hi"] else "en"
    if lang == "hi":
        target_lang = "hi"

    # Prioritize unanswered safety-critical slots
    # 1. Breathing difficulty
    if slots.get("breathing_difficulty") is None and any(s in slots.get("symptoms", []) for s in ["cough", "fever", "breathlessness"]):
        cfg = slots_config.get("breathing_difficulty", {})
        q = cfg.get("question", {}).get(target_lang, cfg.get("question", {}).get("en", "Is there any difficulty in breathing?"))
        opts = cfg.get("options", ["Yes", "No", "Not sure"])
        return q, opts

    # 2. Chest pain
    if slots.get("chest_pain") is None:
        cfg = slots_config.get("chest_pain", {})
        q = cfg.get("question", {}).get(target_lang, cfg.get("question", {}).get("en", "Is the patient experiencing any chest pain?"))
        opts = cfg.get("options", ["Yes", "No", "Not sure"])
        return q, opts

    # 3. Duration
    if slots.get("duration") is None:
        cfg = slots_config.get("duration", {})
        q = cfg.get("question", {}).get(target_lang, cfg.get("question", {}).get("en", "How long has this issue been going on?"))
        opts = cfg.get("options", ["Just started today", "1-3 days", "More than 5 days"])
        return q, opts

    # 4. Severity
    cfg = slots_config.get("severity", {})
    q = cfg.get("question", {}).get(target_lang, cfg.get("question", {}).get("en", "How severe is the discomfort right now?"))
    opts = cfg.get("options", ["Mild", "Moderate", "Severe"])
    return q, opts
