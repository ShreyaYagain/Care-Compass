"""Semantic red-flag screen: meaning-based emergency detection.

Runs AFTER the keyword rules and BEFORE the classifier. Groq assesses the nine
official red flags with a strict JSON schema; a flag is only used if it is
`present=true` AND its `evidence_quote` is a real substring of the user's
message. A present flag becomes a single CONFIRMATION QUESTION from the closed
question bank — the LLM never decides an emergency by itself and never lowers a
rule-based decision.

On Groq failure/timeout, a local per-flag TF-IDF classifier (trained on our
red-flag sentences + augmented paraphrases) supplies the same "ask, don't
decide" signal.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.core.language import normalise_text
from app.core.llm import groq_json, is_groq_available

logger = logging.getLogger(__name__)

# Flags for which a "Not sure" confirmation answer is treated as "Yes".
NOT_SURE_AS_YES = {
    "chest_pain", "breathlessness", "unconsciousness", "severe_bleeding",
    "stroke_symptoms", "seizure", "high_fever_infant",
}

FLAG_TO_QUESTION = {
    "chest_pain": "chest_pain_check",
    "breathlessness": "breathing_difficulty",
    "unconsciousness": "consciousness_check",
    "severe_bleeding": "bleeding_check",
    "stroke_symptoms": "stroke_check",
    "seizure": "seizure_check",
    "high_fever_infant": "infant_fever_age_check",
    "suicidal_ideation": "suicidal_check",
    "severe_dehydration": "dehydration_check",
}
QUESTION_TO_FLAG = {v: k for k, v in FLAG_TO_QUESTION.items()}

COMBINED_QUESTION_ID = "combined_red_flag_screen"
WHICH_ONE_QUESTION_ID = "which_red_flag_symptom"

# Keyword -> official flag mapping for combined/which-one answers ("Yes" alone
# doesn't say which emergency is happening; a named symptom does).
COMBINED_CATEGORY_KEYWORDS = [
    ("breathlessness", ["saans", "sans", "breath", "breathing", "dam"]),
    ("chest_pain", ["chest", "seene", "sine", "chhati", "chati", "dabav", "pressure"]),
    ("severe_bleeding", ["bleed", "bleeding", "blood", "khoon", "khun"]),
    ("seizure", ["fit", "fits", "jhatke", "jhatka", "jerk", "shaking", "shake", "daura", "daure", "seizure", "jhatak"]),
    ("unconsciousness", ["faint", "fainted", "fainting", "behoshi", "behosh", "wake", "unconscious", "hosh", "uth"]),
]


def map_combined_category(text: str) -> Optional[str]:
    """Maps a combined-screen answer to an official red flag when the text
    names one of the six categories, else None."""
    norm = normalise_text(text or "")
    for flag, keywords in COMBINED_CATEGORY_KEYWORDS:
        if any(re.search(rf"\b{re.escape(k)}\b", norm) for k in keywords):
            return flag
    return None

# Vague/health words that indicate a health concern (for the Groq-down failsafe),
# beyond the symptoms.yaml lexicon.
_VAGUE_HEALTH_WORDS = {
    "sweat", "sweaty", "sweating", "paseena", "weird", "ajib", "ajeeb", "uneasy",
    "tabiyat", "bimar", "unwell", "sick", "achy", "hurt", "pain", "dard", "takleef",
    "kamzori", "chakkar", "dizzy", "feeling", "mahsoos", "lag", "raha",
}

SYSTEM_PROMPT = (
    "You are a medical safety screener for an Indian home-care routing app. "
    "Read the patient message and, for EACH of the nine official red flags, decide "
    "whether that emergency condition is PRESENT in the message.\n"
    "Official flags: chest_pain, breathlessness, unconsciousness, severe_bleeding, "
    "stroke_symptoms, seizure, high_fever_infant, suicidal_ideation, severe_dehydration.\n"
    "Rules:\n"
    "- Understand meaning, not just keywords. Descriptive phrasing counts: "
    "\"chest feels like someone is sitting on it\" = chest_pain; "
    "\"blood soaking through three towels\" = severe_bleeding; \"he went limp\" = unconsciousness.\n"
    "- Handle negations: \"no chest pain\" = present false for chest_pain.\n"
    "- Family relations (dad, papa, wife, baby) describe the patient, not the caller.\n"
    "- Languages: English, Hindi (Devanagari), Hinglish.\n"
    "- high_fever_infant only when the patient is a baby/infant (<3 months, newborn) with fever.\n"
    "- present must be \"true\", \"false\" or \"unsure\".\n"
    "- evidence_quote: an EXACT substring of the message that supports present=true "
    "(empty string for false/unsure).\n"
    "Return valid JSON: {\"assessments\": [{\"flag\": ..., \"present\": ..., \"evidence_quote\": ...}, ...]} "
    "with exactly one assessment per flag."
)


class FlagAssessment(BaseModel):
    flag: str
    present: str = "false"
    evidence_quote: str = ""

    @field_validator("present", mode="before")
    @classmethod
    def _coerce_present(cls, v):
        v = str(v).strip().lower()
        if v in ("true", "yes", "y", "present", "1"):
            return "true"
        if v in ("unsure", "maybe", "not sure", "unknown", "?"):
            return "unsure"
        return "false"


class SemanticScreenOut(BaseModel):
    assessments: list[FlagAssessment] = Field(default_factory=list)


def _quote_is_evidence(quote: str, text: str) -> bool:
    if not quote or not quote.strip():
        return False
    q = normalise_text(quote)
    t = normalise_text(text)
    if len(q) < 4:
        return False
    return q in t


def _validate(text: str, out: SemanticScreenOut) -> list[str]:
    flags: list[str] = []
    seen: set[str] = set()
    for a in out.assessments:
        flag = (a.flag or "").strip()
        if flag not in settings.RED_FLAGS or flag in seen:
            continue
        seen.add(flag)
        if a.present != "true":
            continue
        if _quote_is_evidence(a.evidence_quote, text):
            flags.append(flag)
    return flags


def _groq_screen(text: str) -> list[str] | None:
    """Screens with Groq under a hard 2.5 s per-call budget (fast model),
    retrying ONCE on any error / timeout / rate limit. Returns None when the
    screen cannot be completed, so the caller falls back to the local
    classifier and then the combined failsafe question."""
    models = [
        settings.GROQ_FAST_MODEL or settings.GROQ_MODEL,
        settings.GROQ_MODEL or "llama-3.3-70b-versatile",
    ]
    for attempt, model in enumerate(models):
        if not model or (attempt > 0 and model == models[0]):
            break
        try:
            out = groq_json(system=SYSTEM_PROMPT, user=f"Patient message: \"{text}\"",
                            schema=SemanticScreenOut, model=model,
                            timeout=settings.SCREEN_TIMEOUT_S, retries=0)
            if out is not None:
                return _validate(text, out)
        except Exception as e:
            logger.warning(f"Semantic screen Groq call failed ({model}, attempt {attempt + 1}): {e}")
        # groq_json returns None on timeout/429/schema errors too; the loop
        # above is the ONE retry the screen is allowed before falling back.
    return None


# ---------------------------------------------------------------------------
# Local TF-IDF fallback (trained by ml/train_semantic_fallback.py)
# ---------------------------------------------------------------------------

_fallback: Optional[dict] = None
_SCREEN_CACHE: dict[str, list[str]] = {}


def _load_fallback() -> Optional[dict]:
    global _fallback
    if _fallback is None:
        try:
            import joblib
            path = settings.ARTIFACTS_DIR / "semantic_fallback.joblib"
            if path.exists():
                _fallback = joblib.load(path)
            else:
                _fallback = {}
        except Exception as e:
            logger.warning(f"Could not load semantic fallback: {e}")
            _fallback = {}
    return _fallback


def _local_screen(text: str) -> list[str]:
    fb = _load_fallback()
    if not fb:
        return []
    try:
        vec = fb["vectorizer"]
        norm = normalise_text(text)
        x = vec.transform([norm])
        flags = []
        for flag in settings.RED_FLAGS:
            entry = fb["classifiers"].get(flag)
            if not entry:
                continue
            clf, thr = entry["clf"], entry["threshold"]
            p = float(clf.predict_proba(x)[0][1])
            if p >= thr:
                flags.append(flag)
        return flags
    except Exception as e:
        logger.warning(f"Local semantic fallback failed: {e}")
        return []


_SERVICE_SYMPTOM_NAMES = {"nursing_procedure", "lab_test", "teleconsultation_query"}


def _has_health_concern(text: str) -> bool:
    """Lightweight, deterministic check that the message describes a health
    concern (not a pure service request or off-topic). Used only for the
    Groq-down failsafe so we ask a combined screening question instead of
    deciding silently."""
    norm = normalise_text(text)
    tokens = set(norm.split())
    try:
        import yaml
        with open(settings.SYMPTOMS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for name, info in (data.get("symptoms_list") or {}).items():
            if name in _SERVICE_SYMPTOM_NAMES:
                continue
            for syn in [name] + list(info.get("synonyms", []) or []):
                s = normalise_text(syn)
                if s and re.search(rf"\b{re.escape(s)}\b", norm):
                    return True
    except Exception:
        pass
    return any(w in tokens for w in _VAGUE_HEALTH_WORDS)


_LAST_SCREEN_STATUS: str = "skip"


def get_screen_status() -> str:
    """Status of the most recent screen run, for /health & debug:
    groq_ok | fallback_local | failsafe_question | skip."""
    return _LAST_SCREEN_STATUS


def screen_red_flags(text: str, lang: str = "en") -> dict:
    """Assesses the nine official red flags. Returns:
        {"status": "groq_ok"|"fallback_local"|"failsafe_question"|"skip",
         "flags": [...], "combined": bool}

    Never escalates by itself; the caller turns flags/combined into questions.
    Results are memoized per normalized text.
    """
    global _LAST_SCREEN_STATUS
    if not text or not text.strip():
        return {"status": "skip", "flags": [], "combined": False}
    key = normalise_text(text)
    if key in _SCREEN_CACHE:
        cached = _SCREEN_CACHE[key]
        _LAST_SCREEN_STATUS = cached.get("status", "skip")
        return cached

    result: dict = {"status": "skip", "flags": [], "combined": False}

    if is_groq_available():
        flags = _groq_screen(text)
        if flags is not None:
            result = {"status": "groq_ok", "flags": flags, "combined": False}
        else:
            # Groq failed (after the single retry): local TF-IDF fallback.
            flags = _local_screen(text)
            if flags:
                result = {"status": "fallback_local", "flags": flags, "combined": False}
            elif _has_health_concern(text):
                result = {"status": "failsafe_question", "flags": [], "combined": True}
    else:
        flags = _local_screen(text)
        if flags:
            result = {"status": "fallback_local", "flags": flags, "combined": False}
        elif _has_health_concern(text):
            result = {"status": "failsafe_question", "flags": [], "combined": True}

    _LAST_SCREEN_STATUS = result["status"]
    _SCREEN_CACHE[key] = result
    return result


def flag_question_id(flag: str) -> Optional[str]:
    return FLAG_TO_QUESTION.get(flag)


def combined_question_id() -> str:
    return COMBINED_QUESTION_ID
