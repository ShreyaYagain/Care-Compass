import re
import yaml
from typing import Optional, Literal
from pydantic import BaseModel, Field
from pathlib import Path
from app.config import settings
from app.core.language import normalise_text, is_phrase_negated
from app.core.llm import groq_json, is_llm_available

_SYMPTOMS_CONFIG: dict = {}


class GroqSlotExtraction(BaseModel):
    symptoms: list[str] = Field(default_factory=list)
    service_requested: Literal["nursing", "lab", "doctor", "home_check", "none"] = "none"
    who_for: Optional[str] = None
    age_group: Optional[str] = None
    duration: Optional[str] = None
    red_flag_candidates: list[str] = Field(default_factory=list)
    language: Optional[str] = "en"
    confidence: float = 0.8
    unfamiliar_care_type_mapped: Optional[str] = None
    unfamiliar_reason: Optional[str] = None


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
        "service_requested": "none",
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
        "unfamiliar_care_type_mapped": None,
        "unfamiliar_reason": None,
    }


# ---------------------------------------------------------------------------
# Closed question bank (single source of truth: app/data/symptoms.yaml)
# ---------------------------------------------------------------------------

_QUESTION_BANK: list[dict] = []

# Allowed bank ids. The code rejects anything else.
ALLOWED_QUESTION_IDS = [
    "breathing_difficulty",
    "chest_pain_check",
    "consciousness_check",
    "bleeding_check",
    "who_for_age_group",
    "main_symptom_buttons",
    "duration_days",
    "infant_fever_age_check",
    "dehydration_check",
]

# Keyword fallback used to derive asked_ids from historical assistant texts that
# predate the bank (or are verified rephrases of a bank item).
_BANK_ID_KEYWORDS = {
    "breathing_difficulty": ["saans", "breathing", "breath"],
    "chest_pain_check": ["chest", "seene"],
    "consciousness_check": ["hosh", "conscious", "responding", "respond"],
    "bleeding_check": ["bleeding", "khoon", "blood"],
    "who_for_age_group": ["who is this", "kiske liye", "who for", "kiski", "consultation for"],
    "main_symptom_buttons": ["main samasya", "lakshan", "symptom", "problem", "concern"],
    "duration_days": ["kab se", "how long", "duration", "kitne din", "kitne samay"],
    "infant_fever_age_check": ["3 mahine", "3 months", "newborn", "navjat"],
    "dehydration_check": ["peshab", "urine", "dehydration", "paani"],
}


def _load_question_bank() -> list[dict]:
    global _QUESTION_BANK
    if not _QUESTION_BANK and settings.SYMPTOMS_FILE.exists():
        try:
            with open(settings.SYMPTOMS_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _QUESTION_BANK = data.get("question_bank", []) or []
        except Exception:
            _QUESTION_BANK = []
    return _QUESTION_BANK


def _bank_item(qid: str) -> dict | None:
    for item in _load_question_bank():
        if item.get("id") == qid:
            return item
    return None


def _lang_key(lang: str | None) -> str:
    return lang if lang in ("en", "hi", "hinglish") else "en"


def get_question_by_id(qid: str, lang: str = "en") -> tuple[str | None, list[str]]:
    """Returns (question_text, options) localised for lang, or (None, []) if unknown id."""
    item = _bank_item(qid)
    if not item:
        return None, []
    key = _lang_key(lang)
    text = item.get(f"text_{key}") or item.get("text_en") or ""
    opts = []
    for o in item.get("options", []) or []:
        if isinstance(o, dict):
            opts.append(o.get(key) or o.get("en") or "")
        else:
            opts.append(str(o))
    return text, opts


def question_ids() -> list[str]:
    return [item.get("id") for item in _load_question_bank()]


def is_bank_question(text: str | None, lang: str | None = None) -> str | None:
    """Returns the bank id if `text` exactly matches a bank item, else None."""
    if not text:
        return None
    t = text.strip().lower()
    for item in _load_question_bank():
        for key in ("en", "hi", "hinglish"):
            if (item.get(f"text_{key}") or "").strip().lower() == t:
                return item.get("id")
    return None


def count_assistant_turns(history: list[dict] | None) -> int:
    return sum(1 for m in (history or []) if m.get("role") == "assistant")


def get_asked_ids(history: list[dict] | None) -> list[str]:
    """Derives the bank ids already asked, from assistant messages in history."""
    asked: list[str] = []
    for msg in history or []:
        if msg.get("role") != "assistant":
            continue
        t = (msg.get("text") or msg.get("content") or "").lower()
        qid = is_bank_question(t)
        if qid:
            if qid not in asked:
                asked.append(qid)
            continue
        for bid, kws in _BANK_ID_KEYWORDS.items():
            if any(k in t for k in kws):
                if bid not in asked:
                    asked.append(bid)
                break
    return asked


def enforce_question_bank(q_text: str, lang: str = "en", default_id: str = "main_symptom_buttons") -> str:
    """Rejects any follow-up question text that is not a bank item (or a verified
    rephrase), replacing it with the deterministic bank text."""
    if is_bank_question(q_text, lang):
        return q_text
    default_text, _ = get_question_by_id(default_id, lang)
    return default_text or q_text


def _mmcqs_fewshot_snippet(limit: int = 10) -> str:
    """Loads short MMCQS query->summary examples (ml/external/mmcqs_fewshot.json,
    generated by ml/external/mmcqs_fewshot.py) to enrich the Groq extraction prompt.
    Returns '' if the file is absent (the examples are not redistributed)."""
    import json as _json
    fewshot_path = Path(__file__).resolve().parent.parent.parent / "ml" / "external" / "mmcqs_fewshot.json"
    if not fewshot_path.exists():
        return ""
    try:
        with open(fewshot_path, "r", encoding="utf-8") as f:
            examples = _json.load(f)
    except Exception:
        return ""
    if not examples:
        return ""
    lines = ["\nADDITIONAL COMPLAINT->SUMMARY EXAMPLES (extract the main complaint and symptoms):"]
    for ex in examples[:limit]:
        q = (ex.get("query") or "").strip().replace("\n", " ")
        s = (ex.get("summary") or "").strip().replace("\n", " ")
        if q and s:
            lines.append(f"Input: '{q[:180]}'\nMain complaint: {s[:120]}")
    return "\n".join(lines)


def rule_based_extract(text: str, history: list[dict] = None) -> dict:
    """
    Deterministic rule/regex slot extraction fallback.
    Accurately handles multi-turn conversation and follow-up answers (Yes/No/Not sure).
    """
    _load_symptoms_config()
    slots = default_slots()

    bare_answers = {
        "no", "nahi", "nahin", "na", "nope", "n",
        "yes", "haan", "ha", "yup", "y", "ji haan",
        "not sure", "pata nahi", "unsure", "malum nahi", "samajh nahi"
    }

    if history:
        for i, msg in enumerate(history):
            if msg.get("role") == "assistant":
                q_text = (msg.get("text") or msg.get("content") or "").lower()
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

                # Who for follow-up
                if any(w in q_text for w in ["who is this", "kiske liye", "who for", "kiska"]):
                    if any(w in ans_norm for w in ["self", "apne", "mere", "mera", "mujhe", "me"]):
                        slots["patient_relation"] = "self"
                        slots["age_group"] = "adult"
                    elif any(w in ans_norm for w in ["child", "bacha", "baccha", "baby", "<5"]):
                        slots["patient_relation"] = "child"
                        slots["age_group"] = "child"
                    elif any(w in ans_norm for w in ["elderly", "parent", "bujurg", "papa", "mummy", "dada", "dadi", "senior"]):
                        slots["patient_relation"] = "senior"
                        slots["age_group"] = "senior"

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
        "dadi": "grandmother", "nani": "grandmother", "dada": "grandfather", "nanaji": "grandfather",
        "bachha": "child", "bachhe": "child", "beta": "child", "beti": "child", "baby": "child", "child": "child",
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
            if re.search(rf"\b{re.escape(syn_norm)}\b", norm):
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

    # Additional symptoms & complaints
    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["sir dard", "sar dard", "headache", "migraine"]):
        if "headache" not in detected_symptoms:
            detected_symptoms.append("headache")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["pet dard", "pet me dard", "pet mein dard", "stomach pain", "stomach ache", "abdominal pain", "pet kharab"]):
        if "stomach_pain" not in detected_symptoms:
            detected_symptoms.append("stomach_pain")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["moch", "sprain", "twisted ankle", "knee hurts", "ghutne mein dard", "joint pain", "stairs", "chot", "injury", "pain"]):
        if "joint_pain" not in detected_symptoms:
            detected_symptoms.append("joint_pain")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["ghabrahat", "anxiety", "restlessness", "palpitation"]):
        if "restlessness" not in detected_symptoms:
            detected_symptoms.append("restlessness")

    # Service intents & procedures
    combined_lower = combined_text.lower()
    if any(re.search(rf"\b{re.escape(w)}\b", norm) or re.search(rf"\b{re.escape(w)}\b", combined_lower) for w in ["injection", "im injection", "iv drip", "drip", "dressing", "patti", "catheter", "tanke", "stitches", "bedsore", "wound cleaning", "ghaav", "wound"]):
        slots["service_requested"] = "nursing"
        if "nursing_procedure" not in detected_symptoms:
            detected_symptoms.append("nursing_procedure")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) or re.search(rf"\b{re.escape(w)}\b", combined_lower) for w in ["full body checkup", "checkup", "blood test", "sample collection", "home collection", "phlebotomy", "blood sample", "lipid profile", "sugar check", "sugar test", "blood sugar", "diabetes check", "diabetes test", "lab test", "lab"]):
        slots["service_requested"] = "lab"
        if "lab_test" not in detected_symptoms:
            detected_symptoms.append("lab_test")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) or re.search(rf"\b{re.escape(w)}\b", combined_lower) for w in ["second opinion", "dawai", "medicine advice", "prescription", "consultation", "doctor video consult", "bache ki dawai", "dawai par", "kuch aur", "something else"]):
        slots["service_requested"] = "doctor"
        if "teleconsultation_query" not in detected_symptoms:
            detected_symptoms.append("teleconsultation_query")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["kamzor", "buzurg", "elderly", "weak"]):
        if slots["patient_relation"] == "self":
            slots["patient_relation"] = "senior"
        slots["age_group"] = "senior"

    slots["is_vague_doctor_request"] = bool(
        re.search(r"\b(doctor chahiye|need doctor|consult doctor|doctor please)\b", norm)
        and not any(s in detected_symptoms for s in ["headache", "stomach_pain", "fever", "cough", "nursing_procedure", "lab_test", "teleconsultation_query", "joint_pain", "restlessness"])
    )

    slots["symptoms"] = detected_symptoms

    # Breathing & chest pain direct keywords
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

    # Severity keywords
    if any(re.search(rf"\b{w}\b", norm) for w in ["halka", "mild", "thoda", "kam"]):
        slots["severity"] = "mild"
    elif any(re.search(rf"\b{w}\b", norm) for w in ["acute", "tez", "severe", "bahut zyada", "unbearable"]):
        slots["severity"] = "severe"

    # Pregnancy
    if any(re.search(rf"\b{w}\b", norm) for w in ["pregnant", "pregnancy", "garbh", "garbhvati"]):
        slots["pregnancy"] = True

    # Duration
    if any(p in norm for p in ["teen din", "3 din", "3 days", "three days"]):
        slots["duration"] = "3 days"
    elif any(p in norm for p in ["do din", "2 din", "2 days", "two days"]):
        slots["duration"] = "2 days"
    elif any(p in norm for p in ["ek din", "1 din", "1 day", "one day", "kal se", "kal raat se"]):
        slots["duration"] = "1 day"
    elif any(p in norm for p in ["aaj se", "today", "subah se"]):
        slots["duration"] = "today"
    elif any(p in norm for p in ["hafta", "week", "5 din", "5 days", ">5"]):
        slots["duration"] = ">5 days"

    # Chronic conditions
    conditions = []
    if "diabetes" in norm or "sugar" in norm:
        conditions.append("diabetes")
    if "hypertension" in norm or "high bp" in norm or "bp" in norm:
        conditions.append("hypertension")
    if "asthma" in norm or "dama" in norm:
        conditions.append("asthma")
    slots["chronic_conditions"] = conditions

    # Age group
    if slots["patient_relation"] in ["child", "baby"]:
        slots["age_group"] = "child"
    elif slots["patient_relation"] in ["grandmother", "grandfather", "senior", "dada", "dadi"]:
        slots["age_group"] = "senior"

    # Check for explicit age mentions e.g. age 70
    age_match = re.search(r"\b(?:age|umar|saal)\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:saal|years?)\b", norm)
    if age_match:
        age_num = int(age_match.group(1) or age_match.group(2))
        if age_num < 5:
            slots["age_group"] = "child"
        elif age_num >= 65:
            slots["age_group"] = "senior"
        else:
            slots["age_group"] = "adult"

    return slots


def extract_slots(text: str, history: list[dict] = None) -> dict:
    """
    Extracts structured slots.
    Order of preference: Groq LLM (via groq_json) -> Gemini -> Rule-based fallback.
    Never crashes.
    """
    rule_slots = rule_based_extract(text, history)

    # Attempt Groq intake extraction
    system_prompt = (
        "You are an expert clinical intake parser for CareCompass India.\n"
        "Your role is to extract factual patient slots from colloquial inputs in English, Hindi, and Hinglish.\n"
        "CRITICAL POLICY RULES:\n"
        "1. The assistant routes and classifies directly; it NEVER asks the user to choose their care type or service.\n"
        "2. If the user input mentions ANY symptom, pain, body complaint, injection, dressing, wound, or test, do NOT ask what is needed.\n"
        "3. Map requests directly to the 5 official care types:\n"
        "   - paramedic_home_visit (in-person physical assessment, vitals, mobility, sprains, home check)\n"
        "   - home_nursing (injections, IV drip, wound care, dressing, catheter, bedsores)\n"
        "   - lab_test_home (blood sample, lipid profile, sugar test, full body checkup, diagnostic tests)\n"
        "   - teleconsultation (video doctor consult, fever/cough, rash, stomach ache, prescription, mild illness)\n"
        "   - emergency_112 (severe chest pain, acute breathlessness, stroke, seizure, severe bleeding, unconsciousness)\n"
        "Official red flags: chest_pain, breathlessness, unconsciousness, severe_bleeding, stroke_symptoms, "
        "seizure, high_fever_infant, suicidal_ideation, severe_dehydration.\n"
        "FEW-SHOT EXAMPLES OF DIRECT DECISIONS FROM SYMPTOMS (WITHOUT ASKING WHAT IS NEEDED):\n"
        "Example 1:\n"
        "Input: 'mere dada ji ko kal raat se ghabrahat ho rahi hai'\n"
        "Output: {\"symptoms\": [\"ghabrahat\", \"palpitations\", \"restlessness\"], \"who_for\": \"grandfather\", \"age_group\": \"senior\", \"duration\": \"1 day\", \"red_flag_candidates\": [\"chest_pain\", \"breathlessness\"], \"confidence\": 0.9}\n"
        "Example 2:\n"
        "Input: 'pair mein moch aa gayi hai chalne me dard ho raha hai'\n"
        "Output: {\"symptoms\": [\"sprain\", \"joint pain\", \"difficulty walking\"], \"service_requested\": \"none\", \"who_for\": \"self\", \"duration\": null, \"red_flag_candidates\": [], \"confidence\": 0.9}\n"
        "Example 3:\n"
        "Input: 'sugar check karna hai subah'\n"
        "Output: {\"symptoms\": [\"fasting blood sugar\"], \"service_requested\": \"lab\", \"who_for\": \"self\", \"duration\": null, \"red_flag_candidates\": [], \"confidence\": 0.95}\n"
        "Example 4:\n"
        "Input: 'ghar par aake papa ko injection lagana hai'\n"
        "Output: {\"symptoms\": [\"injection administration\"], \"service_requested\": \"nursing\", \"who_for\": \"father\", \"age_group\": \"senior\", \"red_flag_candidates\": [], \"confidence\": 0.95}\n"
        "Return strictly valid JSON matching the schema."
    )

    # Append short MMCQS complaint->summary examples (complain extraction) if present.
    system_prompt += _mmcqs_fewshot_snippet()

    user_prompt = f"Patient Input: \"{text}\"\nConversation History: {history or []}"

    try:
        groq_result: GroqSlotExtraction | None = groq_json(
            system=system_prompt,
            user=user_prompt,
            schema=GroqSlotExtraction,
            model=settings.GROQ_FAST_MODEL or settings.GROQ_MODEL,
        )
        if groq_result:
            # Merge Groq extractions into slots
            merged_symptoms = list(set(rule_slots["symptoms"] + [s.lower() for s in groq_result.symptoms]))
            rule_slots["symptoms"] = merged_symptoms

            if groq_result.service_requested != "none":
                rule_slots["service_requested"] = groq_result.service_requested
            if groq_result.who_for and rule_slots["patient_relation"] == "self":
                rule_slots["patient_relation"] = groq_result.who_for.lower()
            if groq_result.age_group and not rule_slots.get("age_group"):
                rule_slots["age_group"] = groq_result.age_group.lower()
            if groq_result.duration and not rule_slots.get("duration"):
                rule_slots["duration"] = groq_result.duration
            if groq_result.unfamiliar_care_type_mapped:
                rule_slots["unfamiliar_care_type_mapped"] = groq_result.unfamiliar_care_type_mapped
                rule_slots["unfamiliar_reason"] = groq_result.unfamiliar_reason

            # Handle red flag candidates
            for rf in groq_result.red_flag_candidates:
                if rf == "breathlessness" and rule_slots.get("breathing_difficulty") is None:
                    rule_slots["breathing_difficulty"] = True
                elif rf == "chest_pain" and rule_slots.get("chest_pain") is None:
                    rule_slots["chest_pain"] = True
    except Exception:
        pass

    return rule_slots


def has_question_been_asked(history: list[dict], pattern_words: list[str]) -> bool:
    """Checks if any previous assistant message contains any of the pattern words."""
    if not history:
        return False
    for msg in history:
        if msg.get("role") == "assistant":
            text = (msg.get("text") or msg.get("content") or "").lower()
            if any(w.lower() in text for w in pattern_words):
                return True
    return False


def _select_question_id(slots: dict, history: list[dict] | None, context: dict | None = None) -> str | None:
    """
    Returns the next question bank id to ask, or None if no question is needed.
    The closed bank (app/data/symptoms.yaml) is the ONLY source of questions.
    """
    history = history or []
    asked = get_asked_ids(history)
    assistant_turns = count_assistant_turns(history)
    symptoms = slots.get("symptoms", [])

    has_health_info = bool(
        symptoms
        or slots.get("service_requested") in ["nursing", "lab"]
        or slots.get("unfamiliar_care_type_mapped")
    )

    # (c) No health information at all -> symptom-style clue buttons.
    if not has_health_info:
        return "main_symptom_buttons" if "main_symptom_buttons" not in asked else None

    # (a) Red-flag screens, in priority order. A screen is only asked when it
    # could change the decision; a clear multi-symptom picture (e.g. fever+cough
    # with duration) is decided immediately.
    if (
        slots.get("breathing_difficulty") is None
        and any(s in symptoms for s in ["cough", "fever", "breathlessness", "restlessness"])
        and len(symptoms) == 1
        and not slots.get("duration")
        and "breathing_difficulty" not in asked
    ):
        return "breathing_difficulty"

    if (
        "chest_pain" in symptoms
        and slots.get("chest_pain") is None
        and "chest_pain_check" not in asked
    ):
        return "chest_pain_check"

    # (b) Who it is for / age group, when unknown and it changes risk (acute abdomen).
    if (
        slots.get("patient_relation") == "self"
        and slots.get("age_group") is None
        and "stomach_pain" in symptoms
        and "who_for_age_group" not in asked
    ):
        return "who_for_age_group"

    # (d) Duration, only on an isolated single symptom on the first turn.
    if (
        assistant_turns == 0
        and len(symptoms) == 1
        and symptoms[0] in ["fever", "cough"]
        and not slots.get("duration")
        and "duration_days" not in asked
    ):
        return "duration_days"

    return None


def needs_more_info(slots: dict, history_turns: int, history: list[dict] = None) -> bool:
    """
    Check if a follow-up question is needed, under the strict policy:
    1. Hard turn cap: never more than settings.MAX_FOLLOWUPS assistant questions.
    2. Questions only gather FACTS about the patient, NEVER the care type or service.
    3. Every question must come from the closed bank; no severity / service / treatment
       / scheduling / medicine questions are ever asked.
    `history_turns` is interpreted as the number of assistant turns already asked.
    """
    history = history or []

    # Hard cap: MAX_FOLLOWUPS (2) assistant questions max, then decide.
    if history_turns >= settings.MAX_FOLLOWUPS:
        return False

    return _select_question_id(slots, history) is not None


def select_follow_up_question(
    slots: dict,
    lang: str = "en",
    history: list[dict] = None,
    context: dict | None = None,
) -> tuple[str, list[str]]:
    """
    Selects the next follow-up question from the closed question bank.
    Returns (question_text, options) localised for `lang`.
    NEVER asks the user to choose a care type or service, never asks about
    treatment/scheduling/medicines, and never asks a severity question.
    """
    history = history or []
    qid = _select_question_id(slots, history, context)

    if qid is None:
        # Nothing left to ask: fall back to symptom-style buttons (still a bank item).
        qid = "main_symptom_buttons"

    text, options = get_question_by_id(qid, lang)
    if text is None:
        # Unknown bank id (should never happen): use the main symptom bank item.
        text, options = get_question_by_id("main_symptom_buttons", lang)
    return text, options
