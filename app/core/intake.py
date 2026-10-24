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
    Accurately handles multi-turn conversation and follow-up answers (Yes/No/Not sure).
    """
    _load_symptoms_config()
    slots = default_slots()

    # Identify previous assistant questions and corresponding user answers
    bare_answers = {
        "no", "nahi", "nahin", "na", "nope", "n",
        "yes", "haan", "ha", "yup", "y", "ji haan",
        "not sure", "pata nahi", "unsure", "malum nahi", "samajh nahi"
    }

    if history:
        for i, msg in enumerate(history):
            if msg.get("role") == "assistant":
                q_text = (msg.get("text") or msg.get("content") or "").lower()
                # Find subsequent user answer
                ans_text = ""
                for j in range(i + 1, len(history)):
                    if history[j].get("role") == "user":
                        ans_text = (history[j].get("text") or history[j].get("content") or "").lower()
                        break
                if not ans_text:
                    ans_text = text.lower()

                ans_norm = normalise_text(ans_text)
                is_neg = any(w in ans_norm.split() for w in ["no", "nahi", "nahin", "na"]) or "dikkat nahi" in ans_norm or "dard nahi" in ans_norm
                is_pos = (any(w in ans_norm.split() for w in ["yes", "haan", "ha", "ji haan"]) or "dikkat hai" in ans_norm or "dard hai" in ans_norm) and not is_neg
                is_unsure = any(w in ans_norm for w in ["not sure", "pata nahi", "malum nahi", "unsure"])

                # Breathing follow-up
                if any(w in q_text for w in ["saans", "breathing", "breath"]):
                    if is_pos:
                        slots["breathing_difficulty"] = True
                    elif is_neg:
                        slots["breathing_difficulty"] = False
                    elif is_unsure:
                        slots["breathing_difficulty"] = None

                # Chest pain follow-up
                if any(w in q_text for w in ["chest", "seene"]):
                    if is_pos:
                        slots["chest_pain"] = True
                    elif is_neg:
                        slots["chest_pain"] = False
                    elif is_unsure:
                        slots["chest_pain"] = None

    # Collect substantive user utterances (ignoring bare follow-up replies like "No")
    user_texts = []
    if history:
        for msg in history:
            if msg.get("role") == "user":
                t = (msg.get("text") or msg.get("content") or "").strip()
                if normalise_text(t) not in bare_answers and len(t) > 0:
                    user_texts.append(t)

    norm_curr = normalise_text(text).strip()
    if norm_curr not in bare_answers and len(norm_curr) > 0:
        user_texts.append(text)

    combined_text = " ".join(user_texts)
    norm = normalise_text(combined_text)

    # 1. Relation detection
    relations = {
        "papa": "father", "pitaji": "father", "father": "father",
        "mummy": "mother", "mataji": "mother", "maa": "mother", "mother": "mother",
        "dadi": "grandmother", "nani": "grandmother", "dada": "grandfather",
        "bachha": "child", "bachhe": "child", "beta": "child", "beti": "child", "baby": "child", "child": "child",
        "patni": "wife", "wife": "wife", "pati": "husband", "husband": "husband"
    }
    for word, rel in relations.items():
        if re.search(rf"\b{word}\b", norm):
            slots["patient_relation"] = rel
            break

    # 2. Symptom discovery from user messages
    symptoms_list = _SYMPTOMS_CONFIG.get("symptoms_list", {})
    detected_symptoms = []
    for sym_name, sym_info in symptoms_list.items():
        syns = sym_info.get("synonyms", [])
        for syn in syns:
            syn_norm = normalise_text(syn)
            if re.search(rf"\b{re.escape(syn_norm)}\b", norm):
                # Check negation in combined user utterances
                if is_phrase_negated(syn, combined_text):
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

    # Additional common symptom and service keywords
    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["sir dard", "sar dard", "headache", "migraine"]):
        if "headache" not in detected_symptoms:
            detected_symptoms.append("headache")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["pet dard", "pet me dard", "pet mein dard", "stomach pain", "stomach ache", "abdominal pain", "abdomen pain", "pet kharab"]):
        if "stomach_pain" not in detected_symptoms:
            detected_symptoms.append("stomach_pain")

    # Service intents
    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["injection", "im injection", "iv drip", "drip", "dressing", "patti", "catheter", "tanke", "stitches", "bedsore", "wound cleaning"]):
        if "nursing_procedure" not in detected_symptoms:
            detected_symptoms.append("nursing_procedure")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["full body checkup", "checkup", "blood test", "sample collection", "home collection", "phlebotomy", "blood sample", "lipid profile"]):
        if "lab_test" not in detected_symptoms:
            detected_symptoms.append("lab_test")

    # If the user only said "doctor chahiye" without symptom, don't treat "doctor" as symptom
    slots["is_vague_doctor_request"] = bool(
        re.search(r"\b(doctor chahiye|need doctor|consult doctor|doctor please)\b", norm)
        and not any(s in detected_symptoms for s in ["headache", "stomach_pain", "fever", "cough", "nursing_procedure", "lab_test"])
    )

    slots["symptoms"] = detected_symptoms

    # 3. Direct checks for breathing & chest pain if not explicitly set
    if slots["breathing_difficulty"] is None:
        if any(re.search(rf"\b{w}\b", norm) for w in ["breathing", "saans", "sans"]):
            if is_phrase_negated("saans", combined_text) or is_phrase_negated("breathing", combined_text):
                slots["breathing_difficulty"] = False
            elif any(w in norm for w in ["dikkat", "takleef", "difficulty", "shortness"]):
                slots["breathing_difficulty"] = True

    if slots["chest_pain"] is None:
        if any(w in norm for w in ["chest pain", "seene me dard", "seene mein dard"]):
            if is_phrase_negated("chest pain", combined_text) or is_phrase_negated("seene", combined_text):
                slots["chest_pain"] = False
            else:
                slots["chest_pain"] = True

    # 4. Severity detection
    if any(re.search(rf"\b{w}\b", norm) for w in ["halka", "mild", "thoda", "kam"]):
        slots["severity"] = "mild"
    elif any(re.search(rf"\b{w}\b", norm) for w in ["acute", "tez", "severe", "bahut zyada", "unbearable"]):
        slots["severity"] = "severe"

    # Pregnancy detection
    if any(re.search(rf"\b{w}\b", norm) for w in ["pregnant", "pregnancy", "garbh", "garbhvati"]):
        slots["pregnancy"] = True

    # 5. Duration
    if any(p in norm for p in ["teen din", "3 din", "3 days", "three days"]):
        slots["duration"] = "3 days"
    elif any(p in norm for p in ["do din", "2 din", "2 days", "two days"]):
        slots["duration"] = "2 days"
    elif any(p in norm for p in ["ek din", "1 din", "1 day", "one day", "kal se"]):
        slots["duration"] = "1 day"
    elif any(p in norm for p in ["aaj se", "today", "subah se"]):
        slots["duration"] = "today"
    elif any(p in norm for p in ["hafta", "week", "5 din", "5 days", ">5"]):
        slots["duration"] = ">5 days"

    # 6. Chronic conditions
    conditions = []
    if "diabetes" in norm or "sugar" in norm:
        conditions.append("diabetes")
    if "hypertension" in norm or "high bp" in norm or "bp" in norm:
        conditions.append("hypertension")
    if "asthma" in norm or "dama" in norm:
        conditions.append("asthma")
    slots["chronic_conditions"] = conditions

    # 7. Age group
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
    Max 4 turns.
    Rule: Empty, vague, or generic queries without symptom or service ("doctor chahiye") need follow-up.
    """
    if history_turns >= settings.MAX_FOLLOWUPS:
        return False

    symptoms = slots.get("symptoms", [])

    if slots.get("is_vague_doctor_request"):
        return True

    # Rule G: If no symptoms or services extracted -> ask to describe the problem
    if not symptoms:
        return True

    # If single isolated symptom without duration and without patient relation / severity
    # on first turn, ask clarifying question (e.g. "fever" alone)
    if (
        history_turns == 0
        and len(symptoms) == 1
        and symptoms[0] in ["fever", "cough"]
        and not slots.get("duration")
        and not slots.get("severity")
        and slots.get("breathing_difficulty") is None
    ):
        return True

    # If chest pain specifically mentioned but clarity is unknown
    if "chest_pain" in symptoms and slots.get("chest_pain") is None:
        return True

    return False


def select_follow_up_question(slots: dict, lang: str = "en") -> tuple[str, list[str]]:
    """
    Select follow-up question based on safety priority and user intent.
    """
    _load_symptoms_config()
    slots_config = _SYMPTOMS_CONFIG.get("slots", {})

    target_lang = "hi" if lang == "hi" else ("hinglish" if lang == "hinglish" else "en")
    symptoms = slots.get("symptoms", [])

    if slots.get("is_vague_doctor_request"):
        if lang == "hi":
            return (
                "हम सहायता के लिए तैयार हैं — यह किसके लिए है और मुख्य परेशानी क्या है (बुखार, चोट, लैब टेस्ट या डॉक्टर परामर्श)?",
                ["बुखार", "चोट", "लैब टेस्ट", "डॉक्टर परामर्श"],
            )
        else:
            return (
                "Happy to help — who is this for and what's the main concern (fever, injury, a lab test, or just a doctor consult)?",
                ["Fever", "Injury", "Lab test", "Doctor consult"],
            )

    # Empty or no symptoms
    if not symptoms:
        if lang == "hi":
            return "क्या परेशानी है? कृपया हमें मुख्य लक्षण बताएं।", ["बुखार", "खांसी", "सिर दर्द", "पेट दर्द", "अन्य"]
        elif lang == "hinglish":
            return "Kya pareshani hai? Kripya mukhya lakshan batayein.", ["Fever", "Cough", "Headache", "Stomach pain", "Other"]
        else:
            return "What is the problem? Please tell us the main symptom.", ["Fever", "Cough", "Headache", "Stomach pain", "Other"]

    # 1. Breathing difficulty if respiratory symptoms present
    if slots.get("breathing_difficulty") is None and any(s in symptoms for s in ["cough", "fever", "breathlessness"]):
        cfg = slots_config.get("breathing_difficulty", {})
        q = cfg.get("question", {}).get(target_lang, cfg.get("question", {}).get("en", "Is there any difficulty in breathing?"))
        opts = cfg.get("options", ["Yes", "No", "Not sure"])
        return q, opts

    # 2. Chest pain ONLY if chest_pain was mentioned
    if "chest_pain" in symptoms and slots.get("chest_pain") is None:
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
