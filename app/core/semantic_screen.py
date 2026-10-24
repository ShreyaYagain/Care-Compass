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
    model_chain = [
        settings.GROQ_FAST_MODEL,
        settings.GROQ_MODEL,
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ]
    for model in model_chain:
        if not model:
            continue
        try:
            out = groq_json(system=SYSTEM_PROMPT, user=f"Patient message: \"{text}\"",
                            schema=SemanticScreenOut, model=model)
            if out is not None:
                return _validate(text, out)
        except Exception as e:
            logger.warning(f"Semantic screen Groq call failed ({model}): {e}")
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


def screen_red_flags(text: str, lang: str = "en") -> list[str]:
    """Returns the official flags the semantic screen considers PRESENT.

    Never escalates by itself; the caller turns these into confirmation questions.
    Results are memoized per normalized text (one LLM call per unique message).
    """
    if not text or not text.strip():
        return []
    key = normalise_text(text)
    if key in _SCREEN_CACHE:
        return _SCREEN_CACHE[key]
    if is_groq_available():
        flags = _groq_screen(text)
        if flags is not None:
            _SCREEN_CACHE[key] = flags
            return flags
    flags = _local_screen(text)
    _SCREEN_CACHE[key] = flags
    return flags


def flag_question_id(flag: str) -> Optional[str]:
    return FLAG_TO_QUESTION.get(flag)
