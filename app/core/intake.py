import re
import yaml
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from pathlib import Path
from app.config import settings
from app.core.language import normalise_text, is_phrase_negated
from app.core.llm import llm_json, is_llm_available, llm_fast_model

_SYMPTOMS_CONFIG: dict = {}


class SlotExtraction(BaseModel):
    symptoms: list[str] = Field(default_factory=list)
    service_requested: str = "none"
    who_for: Optional[str] = None
    age_group: Optional[str] = None
    duration: Optional[str] = None
    duration_evidence: Optional[str] = None
    fever_temp: Optional[float] = None
    fever_temp_unit: Optional[str] = None
    fever_temp_evidence: Optional[str] = None
    age_evidence: Optional[str] = None
    red_flag_candidates: list[str] = Field(default_factory=list)
    language: Optional[str] = "en"
    confidence: float = 0.8
    unfamiliar_care_type_mapped: Optional[str] = None
    unfamiliar_reason: Optional[str] = None

    @field_validator("service_requested", mode="before")
    @classmethod
    def _coerce_service(cls, v):
        if v in ("nursing", "lab", "doctor", "home_check", "none"):
            return v
        # The LLM sometimes returns a care_type (e.g. emergency_112) here; map it
        # to a service intent or leave "none" so the rule layer decides.
        return "none"


def _load_symptoms_config():
    global _SYMPTOMS_CONFIG
    if not _SYMPTOMS_CONFIG and settings.SYMPTOMS_FILE.exists():
        try:
            with open(settings.SYMPTOMS_FILE, "r", encoding="utf-8") as f:
                _SYMPTOMS_CONFIG = yaml.safe_load(f) or {}
        except Exception:
            _SYMPTOMS_CONFIG = {}


def canonicalise_symptom(name: str) -> str | None:
    """
    Validates a raw symptom token against the canonical lexicon (symptoms.yaml).

    Rules:
      - Exact whole-token match against a canonical name or one of its synonyms
        is accepted and mapped to the canonical id.
      - Tokens shorter than 4 characters are rejected unless they are in the
        lexicon (e.g. "gas"-like short synonyms live in the yaml).
      - Everything else (substrings, near-matches, junk fragments like
        "tin"/"ting") is rejected. No loose fuzzy matching below 0.85 similarity.
    """
    if not name:
        return None
    _load_symptoms_config()
    n = normalise_text(str(name)).strip()
    if not n:
        return None

    symptoms_list = _SYMPTOMS_CONFIG.get("symptoms_list", {})
    for canon, info in symptoms_list.items():
        if n == canon:
            return canon
        for syn in info.get("synonyms", []):
            if n == normalise_text(syn):
                return canon

    # Short tokens must be in the lexicon to pass.
    if len(n) < 4:
        return None

    return None


def canonicalise_symptom_list(names: list[str]) -> list[str]:
    """Maps a raw symptom list to canonical ids, dropping unrecognised tokens."""
    out: list[str] = []
    seen = set()
    for raw in names or []:
        canon = canonicalise_symptom(raw)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


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
        "fever_temp_unit": None,
        "pregnancy": False,
        "chronic_conditions": [],
        "unfamiliar_care_type_mapped": None,
        "unfamiliar_reason": None,
        "extraction_source": "lexicon",
    }


# ---------------------------------------------------------------------------
# Number / duration / temperature / age parsing (input-noise rules)
#
# A bare number is never a duration, temperature or age. A number only counts
# when it is directly attached to the right unit or marker, and age vs duration
# are kept apart ("2 saal se dard" = duration, "70 saal ke papa" = age).
# ---------------------------------------------------------------------------

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_HINDI_NUM_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "tina": 3, "chaar": 4, "char": 4,
    "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "chhah": 6,
    "saat": 7, "sath": 7, "aath": 8, "ath": 8, "nau": 9, "das": 10,
}
_EN_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_DURATION_UNITS = {
    "day": ["din", "dina", "dino", "day", "days"],
    "week": ["hafta", "hafte", "week", "weeks", "saptah", "saaptah"],
    "hour": ["ghanta", "ghante", "ghanton", "hour", "hours", "hr", "hrs"],
    "month": ["mahina", "mahine", "mahino", "month", "months"],
    "year": ["saal", "sal", "sala", "varsh", "varash", "year", "years"],
    "night": ["raat", "raaton", "night", "nights"],
}

_YEAR_UNITS = ("saal", "sal", "sala", "varsh", "varash", "year", "years")
_FEVER_WORDS = ("fever", "bukhar", "bukhaar", "bukhara", "taap", "temperature", "jwar", "jvara")


def _normalise_num(text: str) -> str:
    return normalise_text(text or "").translate(_DEV_DIGITS)


def _duration_label(days: int, unit_kind: str) -> str:
    if unit_kind == "hour":
        return "today"
    if unit_kind in ("week", "month", "year"):
        return ">5 days"
    # day / night
    if days == 1:
        return "1 day"
    if days == 2:
        return "2 days"
    if days == 3:
        return "3 days"
    if days == 4:
        return "4 days"
    if days >= 5:
        return ">5 days"
    return "today"


def parse_duration(text: str) -> Optional[str]:
    """Returns a canonical duration label only when a number/number-word is
    attached to a time unit. Bare numbers never produce a duration."""
    norm = _normalise_num(text)
    if not norm:
        return None

    if re.search(r"\bkal raat se\b", norm) or re.search(r"\bkal raat\b", norm):
        return "1 day"
    if re.search(r"\bkal se\b", norm):
        return "1 day"
    if re.search(r"\baaj se\b|\bsubah se\b|\btoday\b|\bsince morning\b|\bmorning se\b", norm):
        return "today"

    numword = "|".join(list(_HINDI_NUM_WORDS) + list(_EN_NUM_WORDS))
    for unit_kind, words in _DURATION_UNITS.items():
        unit_alt = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
        for pat in (rf"\b(\d{{1,3}})\s*({unit_alt})\b", rf"\b({numword})\s+({unit_alt})\b"):
            m = re.search(pat, norm)
            if not m:
                continue
            raw_num = m.group(1)
            if unit_kind == "year":
                after = norm[m.end():]
                if not re.match(r"^\s*(?:se|since|for)\b", after):
                    continue
            if raw_num.isdigit():
                n = int(raw_num)
            else:
                n = _HINDI_NUM_WORDS.get(raw_num, _EN_NUM_WORDS.get(raw_num))
                if n is None:
                    continue
            return _duration_label(n, unit_kind)
    return None


def parse_temperature(text: str) -> Optional[tuple[float, str]]:
    """Temperature only when a number in 95-108 (F) or 35-42 (C) sits next to a
    fever word or a degree marker. Returns (value, "F"|"C") or None."""
    norm = _normalise_num(text)
    if not norm:
        return None
    tokens = norm.split()
    fever = set(_FEVER_WORDS)

    for i, tok in enumerate(tokens):
        m = re.fullmatch(r"(\d{2,3}(?:\.\d+)?)", tok)
        if not m:
            continue
        val = float(m.group(1))
        prev = tokens[i - 1] if i > 0 else ""
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if nxt in ("f", "fahrenheit") or prev in ("f", "fahrenheit"):
            if 95 <= val <= 108:
                return (val, "F")
        if nxt in ("c", "celsius") or prev in ("c", "celsius"):
            if 35 <= val <= 42:
                return (val, "C")

    for i, tok in enumerate(tokens):
        if tok not in fever:
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(tokens):
                m = re.fullmatch(r"(\d{2,3}(?:\.\d+)?)", tokens[j])
                if m:
                    val = float(m.group(1))
                    if 95 <= val <= 108:
                        return (val, "F")
                    if 35 <= val <= 42:
                        return (val, "C")
    return None


def parse_age(text: str) -> Optional[int]:
    """Age from "age 70", "70 saal ke papa", "70 years old", "umar 38".
    Returns None for durations ("2 saal se dard") and bare numbers."""
    norm = _normalise_num(text)
    if not norm:
        return None

    m = re.search(r"\b(?:age|aged|umar|umra)\s*(?:is\s+|of\s+)?(\d{1,3})\b", norm)
    if m:
        return int(m.group(1))

    m = re.search(
        r"\b(\d{1,3})\s*(?:" + "|".join(_YEAR_UNITS) + r")\s*(?:old|ka|ke|ki|kii|hain)\b",
        norm,
    )
    if m:
        return int(m.group(1))

    m = re.search(r"\b(\d{1,3})\s*(?:" + "|".join(_YEAR_UNITS) + r")\b", norm)
    if m:
        after = norm[m.end():]
        if not re.match(r"^\s*(?:se|since|for)\b", after):
            return int(m.group(1))
    return None


def build_classifier_text(slots: dict) -> str:
    """Cleaned classifier input: canonical symptom names + validated slots only.
    Raw user text (with noise tokens) is never fed to the classifier."""
    parts: list[str] = []
    for s in slots.get("symptoms", []) or []:
        parts.append(str(s).replace("_", " "))
    service = slots.get("service_requested")
    if service and service != "none":
        parts.append(str(service).replace("_", " "))
    if slots.get("duration"):
        parts.append(f"duration {slots['duration']}")
    if slots.get("severity"):
        parts.append(str(slots["severity"]))
    if slots.get("age_group"):
        parts.append(str(slots["age_group"]))
    relation = slots.get("patient_relation")
    if relation and relation != "self":
        parts.append(str(relation))
    if slots.get("breathing_difficulty"):
        parts.append("breathing difficulty")
    if slots.get("chest_pain"):
        parts.append("chest pain")
    if slots.get("fever_temp") is not None:
        parts.append(f"temperature {slots['fever_temp']}{slots.get('fever_temp_unit') or ''}")
    return " ".join(parts)


def _evidence_in_text(evidence: Optional[str], text: str) -> bool:
    """True when `evidence` is a real (normalised) substring of `text`."""
    if not evidence or not evidence.strip():
        return False
    ev_norm = normalise_text(evidence)
    if not ev_norm:
        return False
    return ev_norm in normalise_text(text) or evidence.strip() in text


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


def count_asked_id(history: list[dict] | None, qid: str) -> int:
    """Counts how many times `qid` has been asked in history (for the input-noise
    symptom-question budget, which allows the clue buttons up to twice)."""
    kws = _BANK_ID_KEYWORDS.get(qid, [])
    count = 0
    for msg in history or []:
        if msg.get("role") != "assistant":
            continue
        t = (msg.get("text") or msg.get("content") or "").lower()
        if is_bank_question(t) == qid:
            count += 1
        elif kws and any(k in t for k in kws):
            count += 1
    return count


def enforce_question_bank(q_text: str, lang: str = "en", default_id: str = "main_symptom_buttons") -> str:
    """Rejects any follow-up question text that is not a bank item (or a verified
    rephrase), replacing it with the deterministic bank text."""
    if is_bank_question(q_text, lang):
        return q_text
    default_text, _ = get_question_by_id(default_id, lang)
    return default_text or q_text


def _mmcqs_fewshot_snippet(limit: int = 10) -> str:
    """Loads short MMCQS query->summary examples (ml/external/mmcqs_fewshot.json,
    generated by ml/external/mmcqs_fewshot.py) to enrich the LLM extraction prompt.
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
    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["sir dard", "sar dard", "headache", "migraine", "head hurts", "head pain", "head ache", "sir me dard", "sar me dard", "sir mein dard", "sar mein dard"]):
        if "headache" not in detected_symptoms:
            detected_symptoms.append("headache")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["pet dard", "pet me dard", "pet mein dard", "stomach pain", "stomach ache", "abdominal pain", "pet kharab"]):
        if "stomach_pain" not in detected_symptoms:
            detected_symptoms.append("stomach_pain")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["moch", "sprain", "twisted ankle", "knee hurts", "ghutne mein dard", "joint pain", "stairs", "chot", "injury", "pain"]):
        if "joint_pain" not in detected_symptoms:
            detected_symptoms.append("joint_pain")

    # Fall / injury: "I fell down and my leg hurts" -> injury (injury module)
    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["fell", "fell down", "fall", "gir gaya", "gir ke", "gira hai", "giri hai", "gir", "leg hurts", "ankle", "foot", "knee", "hurt", "sprain", "twisted ankle", "swollen", "soojan", "sujan", "swelling", "bruise", "neel", "wrist", "shoulder", "kandha", "kandhe", "elbow", "kohni", "back pain", "back me dard", "back dard", "kamar", "kamar dard", "neck", "gardan", "muscle pain", "bone", "haddi"]):
        if "injury" not in detected_symptoms:
            detected_symptoms.append("injury")

    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["ghabrahat", "anxiety", "restlessness", "palpitation"]):
        if "restlessness" not in detected_symptoms:
            detected_symptoms.append("restlessness")

    # Dizziness (chakkar / dizzy / vertigo) is a real symptom, never "no health info"
    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["dizziness", "dizzy", "vertigo", "chakkar", "ghoomta", "ghoom"]):
        if "dizziness" not in detected_symptoms:
            detected_symptoms.append("dizziness")

    # Weakness / fatigue is a real symptom, never "no health info"
    if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["weakness", "kamzori", "kamjor", "thakan", "thakavat", "fatigue"]):
        if "weakness" not in detected_symptoms:
            detected_symptoms.append("weakness")

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

    # Only canonical symptoms may leave this function.
    slots["symptoms"] = canonicalise_symptom_list(detected_symptoms)

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

    # Severity reflects the MOST serious symptom: severe keywords win over mild
    # keywords (multiple unrelated complaints -> severity of the most serious).
    if any(re.search(rf"\b{w}\b", norm) for w in ["acute", "tez", "severe", "unbearable", "bahut zyada", "bahut", "zyada", "bohot", "intense", "bhayanak"]):
        slots["severity"] = "severe"
    elif any(re.search(rf"\b{w}\b", norm) for w in ["halka", "halki", "mild", "thoda", "kam"]):
        slots["severity"] = "mild"

    # Pregnancy (incl. Devanagari/ITRANS forms of गर्भवती / गर्भावस्था)
    if any(re.search(rf"\b{w}\b", norm) for w in ["pregnant", "pregnancy", "garbh", "garbhvati", "garbhavati", "garbhavastha"]):
        slots["pregnancy"] = True

    # Duration (number/number-word attached to a time unit only; bare numbers
    # never create a duration) and temperature (95-108 F / 35-42 C only).
    slots["duration"] = parse_duration(combined_text)
    temp = parse_temperature(combined_text)
    if temp:
        slots["fever_temp"] = temp[0]
        slots["fever_temp_unit"] = temp[1]

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

    # Check for explicit age mentions e.g. "age 70", "70 saal ke papa",
    # "38 saal", "umra 38" (ITRANS). Age vs duration is kept apart: "2 saal se
    # dard" is a duration, never an age.
    age_num = parse_age(combined_text)
    if age_num is not None:
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
    Order of preference: lexicon/regex FIRST; the LLM (via llm_json) is a
    fallback used only when the lexicon finds no symptom and no service request.
    The returned dict carries `extraction_source` = "lexicon" | "llm".
    Never crashes.
    """
    rule_slots = rule_based_extract(text, history)

    # The LLM is a fallback ONLY when the lexicon found nothing.
    lexicon_found = bool(rule_slots["symptoms"]) or rule_slots.get("service_requested") != "none"
    if lexicon_found:
        return rule_slots

    # Attempt LLM intake extraction (fallback)
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
        llm_result: SlotExtraction | None = llm_json(
            system=system_prompt,
            user=user_prompt,
            schema=SlotExtraction,
            model=llm_fast_model(),
        )
        if llm_result:
            # Merge LLM extractions into slots. Every LLM-returned symptom is
            # validated against the canonical lexicon; junk fragments
            # (substrings like "tin"/"ting") are dropped.
            llm_symptoms = canonicalise_symptom_list(llm_result.symptoms)
            merged_symptoms = list(set(rule_slots["symptoms"] + llm_symptoms))
            rule_slots["symptoms"] = merged_symptoms
            if llm_symptoms:
                rule_slots["extraction_source"] = "llm"

            if llm_result.service_requested != "none":
                rule_slots["service_requested"] = llm_result.service_requested
            if llm_result.who_for and rule_slots["patient_relation"] == "self":
                rule_slots["patient_relation"] = llm_result.who_for.lower()
            if llm_result.age_group and not rule_slots.get("age_group"):
                # Age is accepted only with a re-validated evidence quote.
                if _evidence_in_text(llm_result.age_evidence, text) and parse_age(llm_result.age_evidence) is not None:
                    rule_slots["age_group"] = llm_result.age_group.lower()
            if llm_result.duration and not rule_slots.get("duration"):
                # Duration must come with an evidence quote that is a substring
                # of the message and re-parses with the same regex; else drop.
                if _evidence_in_text(llm_result.duration_evidence, text) and parse_duration(llm_result.duration_evidence) is not None:
                    rule_slots["duration"] = llm_result.duration
            if llm_result.fever_temp is not None and rule_slots.get("fever_temp") is None:
                if _evidence_in_text(llm_result.fever_temp_evidence, text) and parse_temperature(llm_result.fever_temp_evidence) is not None:
                    rule_slots["fever_temp"] = llm_result.fever_temp
                    unit = (llm_result.fever_temp_unit or "").strip().upper()
                    rule_slots["fever_temp_unit"] = unit[:1] if unit[:1] in ("F", "C") else "F"
            if llm_result.unfamiliar_care_type_mapped:
                rule_slots["unfamiliar_care_type_mapped"] = llm_result.unfamiliar_care_type_mapped
                rule_slots["unfamiliar_reason"] = llm_result.unfamiliar_reason

            # Handle red flag candidates
            for rf in llm_result.red_flag_candidates:
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

    Follow-up policy (strict):
      - A question is NEVER asked when the answer is already in the message or
        the conversation history.
      - Pregnancy: never ask, always decide.
      - Symptom (or service request) + any context (severity / duration / age /
        relation / pregnancy / chronic condition) => sufficient, decide.
      - One red-flag screening question at most, and only for symptoms that
        could be serious (stomach pain, headache, dizziness/restlessness).
      - No health information at all => symptom clue buttons (at most once).
    """
    history = history or []
    asked = get_asked_ids(history)
    symptoms = slots.get("symptoms", [])
    service = slots.get("service_requested")

    has_symptom = bool(symptoms)
    has_service = service in ("nursing", "lab")
    has_health_info = has_symptom or has_service or slots.get("unfamiliar_care_type_mapped")

    # Pregnancy is always decided by the pregnancy layer / classifier.
    if slots.get("pregnancy"):
        return None

    # (a) No health information at all -> symptom clue buttons, at most twice
    # (input-noise budget: two empty attempts, then a low-confidence decision).
    if not has_health_info:
        return "main_symptom_buttons" if count_asked_id(history, "main_symptom_buttons") < 2 else None

    # (b) Sufficiency: symptom + context => decide without asking.
    has_context = bool(
        slots.get("severity")
        or slots.get("duration")
        or slots.get("age_group")
        or (slots.get("patient_relation") not in (None, "self", ""))
        or slots.get("pregnancy")
        or slots.get("chronic_conditions")
    )
    if has_symptom and has_context:
        return None

    # (c) At most ONE red-flag screening question, only for symptoms that could
    # be serious. Everything else is decided by the model directly.
    # A plain headache is NOT an emergency candidate: no consciousness
    # screening question for it (loss-of-consciousness indicators are caught
    # by the red-flag layer / semantic screen instead).
    if has_symptom and not has_context:
        if "stomach_pain" in symptoms and "who_for_age_group" not in asked:
            return "who_for_age_group"
        if "restlessness" in symptoms and "consciousness_check" not in asked:
            return "consciousness_check"
        return None

    # (d) Service requested without symptoms: the model decides.
    return None


def needs_more_info(slots: dict, history_turns: int, history: list[dict] = None) -> bool:
    """
    Check if a follow-up question is needed, under the strict policy:
    1. Hard turn cap: never more than settings.MAX_FOLLOWUPS assistant questions.
    2. Symptom + context (severity/duration/age/relation/pregnancy/chronic) is
       sufficient -> decide, never ask.
    3. At most ONE red-flag screening question, only for symptoms that could be
       serious; at most TWO questions when there is no symptom at all.
    4. Questions only gather FACTS; they never ask for the care type or service,
       and never repeat something already stated in the conversation.
    """
    history = history or []

    # Hard cap: MAX_FOLLOWUPS assistant questions max, then decide.
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
