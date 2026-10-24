"""ML red-flag model (multi-label: one binary classifier per flag).

Runs AFTER the deterministic keyword rules and BEFORE the LLM second opinion.
The model decides together with the rules: its positive hits (a flag whose
calibrated probability clears a per-flag threshold tuned for >= 0.90 recall on
a validation split) are turned into the same single confirmation question the
semantic screen already uses. The model never escalates by itself.

Production default: TF-IDF char n-grams (2-5) + LogisticRegression
(redflag_model.joblib). The multilingual-e5-small + LR candidate is trained by
the same script and kept for offline evaluation.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.core.language import normalise_text

logger = logging.getLogger(__name__)

_model: Optional[dict] = None

# Deterministic corroboration guardrails: a flag is kept only when the raw text
# has at least one supporting indicator, so the ML model cannot hallucinate a
# flag the text cannot support (e.g. suicidal_ideation for "asthma + cough",
# seizure for "dizziness", high_fever_infant for an adult father). These mirror
# the keyword rules, not a full match — meaning-based paraphrases still pass.
_FLAG_INDICATORS = {
    "chest_pain": ("chest", "seene", "sine", "chhati", "chati", "dil", "heart", "cardiac", "dabav", "pressure"),
    "breathlessness": ("saans", "sans", "breath", "breathe", "breathing", "brething", "dam", "wheez", "gasp", "short of breath", "phool"),
    "unconsciousness": ("faint", "behosh", "unconscious", "hosh", "passed out", "blackout", "limp", "not responding", "nahi uth", "wake"),
    "severe_bleeding": ("khoon", "khun", "bleed", "blood", "rakt", "rakta"),
    "stroke_symptoms": ("face", "chehra", "munh", "tedha", "droop", "lakwa", "falij", "paralysis", "slurred", "bol nahi", "ek side", "ek taraf"),
    "seizure": ("fit", "jhatke", "jhatka", "seizure", "daura", "daure", "convulsion", "shaking", "shake", "jerk", "jhag", "kampa"),
    "suicidal_ideation": ("suicid", "kill myself", "mar ja", "jan de", "khud ko", "hurt myself", "end my life", "jeena nahi", "aatmahatya", "khatam kar"),
    "severe_dehydration": ("peshab", "urine", "dehydrat", "sunken", "dhas", "paani nahi", "paani nahin", "honth sukh", "dry mouth", "nikal nahi"),
}
_INFANT_WORDS = ("newborn", "infant", "navjat", "shishu", "naya janm", "mahine ke", "mahina ke", "month old", "chote bacche", "chota bacha", "choti bachi", "naya paida")
_FEVER_WORDS = ("bukhar", "fever", "taap", "temperature", "jwar", "jvara")


def _filter_false_positives(text: str, flags: list[str]) -> list[str]:
    """Drop flags the raw text cannot support, using per-flag indicators."""
    if not flags:
        return flags
    norm = normalise_text(text)
    out: list[str] = []
    for flag in flags:
        if flag == "high_fever_infant":
            if not (any(w in norm for w in _INFANT_WORDS) and any(w in norm for w in _FEVER_WORDS)):
                continue
        else:
            indicators = _FLAG_INDICATORS.get(flag)
            if indicators and not any(w in norm for w in indicators):
                continue
        out.append(flag)
    return out


def load_redflag_model() -> Optional[dict]:
    global _model
    if _model is None:
        try:
            import joblib
            path = settings.ARTIFACTS_DIR / "redflag_model.joblib"
            if path.exists():
                _model = joblib.load(path)
            else:
                _model = {}
        except Exception as e:
            logger.warning(f"Could not load red-flag model: {e}")
            _model = {}
    return _model


def predict_probs(text: str) -> dict[str, float]:
    """Returns per-flag calibrated probabilities {flag: prob}."""
    model = load_redflag_model()
    if not model:
        return {}
    try:
        vec = model["vectorizer"]
        x = vec.transform([normalise_text(text)])
        return {
            flag: float(entry["clf"].predict_proba(x)[0][1])
            for flag, entry in model.get("classifiers", {}).items()
        }
    except Exception as e:
        logger.warning(f"Red-flag model inference failed: {e}")
        return {}


def predict_flags(text: str) -> list[str]:
    """Flags whose probability clears their tuned threshold (recall >= 0.9),
    after removing impossible false positives."""
    model = load_redflag_model()
    if not model:
        return []
    probs = predict_probs(text)
    flags = []
    for flag, entry in model.get("classifiers", {}).items():
        if probs.get(flag, 0.0) >= entry.get("threshold", 0.999):
            flags.append(flag)
    return _filter_false_positives(text, flags)
