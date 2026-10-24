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
    """Flags whose probability clears their tuned threshold (recall >= 0.9)."""
    model = load_redflag_model()
    if not model:
        return []
    probs = predict_probs(text)
    flags = []
    for flag, entry in model.get("classifiers", {}).items():
        if probs.get(flag, 0.0) >= entry.get("threshold", 0.999):
            flags.append(flag)
    return flags
