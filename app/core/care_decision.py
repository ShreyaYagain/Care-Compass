"""Weighted ML+LLM care-type decision (DECISION_POLICY=weighted).

Runs the LLM care-type call (deepseek-flash, lowest effort, 6 s timeout, strict
JSON with the five official types + short definitions) alongside the ML model.
The final care type is the highest-weighted:

    Score(type) = 0.4 * ML_prob(type) + 0.6 * LLM_confidence(type)

The LLM only assigns confidence to the single type it picks (0 for the rest).
If the ML top class probability is >= 0.90 the ML class wins outright. On LLM
timeout / invalid JSON / non-enum, the ML result is used unchanged.

Safety is decided elsewhere and is NEVER lowered here: an emergency from a
keyword rule, a nine-flag with evidence, the semantic screen, or the user's
"Yes" cannot be demoted, and an LLM-picked emergency still needs a nine-flag
with evidence.
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.core.llm import llm_json, is_llm_available, llm_fast_model, llm_fast_effort

logger = logging.getLogger(__name__)

_CARE_DEFINITIONS = {
    "paramedic_home_visit": "in-person physical assessment, vitals, mobility or home check",
    "home_nursing": "injection, IV drip, wound care, dressing, catheter or bedsore care",
    "lab_test_home": "blood sample or diagnostic lab tests collected at home",
    "teleconsultation": "video doctor consultation for a mild or routine illness",
    "emergency_112": "life-threatening: severe chest pain, breathlessness, stroke, seizure, severe bleeding, unconsciousness",
}

SYSTEM_PROMPT = (
    "You classify a patient message for an Indian home-care app into EXACTLY ONE "
    "of the five official care types. Return strict JSON:\n"
    "{\"care_type\": <one of the five ids>, \"confidence\": <0.0..1.0>, \"reason\": <short line>}\n"
    "Official care types and short definitions:\n" +
    "\n".join(f"- {k}: {v}" for k, v in _CARE_DEFINITIONS.items()) +
    "\nconfidence is how sure you are that the chosen type is correct. You NEVER "
    "invent a type outside the five. Do not over-triage a mild complaint."
)


class CareDecision(BaseModel):
    care_type: str = ""
    confidence: float = 0.5
    reason: str = ""

    @field_validator("care_type", mode="before")
    @classmethod
    def _coerce_care_type(cls, v):
        return (v or "").strip().lower()

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_conf(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


def llm_care_decision(text: str, timeout: float = 6.0) -> Optional[dict]:
    """Returns {"care_type", "confidence", "reason"} or None on failure/timeout."""
    if not is_llm_available():
        return None
    try:
        out = llm_json(
            system=SYSTEM_PROMPT,
            user=f"Patient message: \"{text}\"",
            schema=CareDecision,
            model=llm_fast_model(),
            timeout=timeout,
            retries=0,
            reasoning_effort=llm_fast_effort(),
            max_tokens=200,
        )
    except Exception as e:
        logger.warning(f"LLM care decision failed: {e}")
        return None
    if out is None:
        return None
    care_type = (out.care_type or "").strip()
    if care_type not in settings.CARE_TYPES:
        logger.warning(f"LLM care decision returned invalid type: {care_type!r}")
        return None
    return {
        "care_type": care_type,
        "confidence": float(out.confidence),
        "reason": (out.reason or "").strip(),
    }


def weighted_care_type(ml_probs: dict[str, float], llm: Optional[dict]) -> tuple[str, dict]:
    """Returns (care_type, decision_meta).

    decision_meta = {"ml": {...}, "llm": {...}|None, "agreed": bool, "used": "ml"|"weighted"}
    """
    ml_top = max(ml_probs, key=ml_probs.get) if ml_probs else None
    ml_top = ml_top if ml_top in settings.CARE_TYPES else None
    ml_decision = {"care_type": ml_top, "probs": dict(ml_probs), "confidence": ml_probs.get(ml_top, 0.0) if ml_top else 0.0}

    meta: dict = {"ml": ml_decision, "llm": None, "agreed": False, "used": "ml"}

    if llm is None or ml_top is None:
        meta["llm"] = llm
        return ml_top or "teleconsultation", meta

    meta["llm"] = llm
    meta["agreed"] = llm["care_type"] == ml_top

    # ML wins outright when very confident in its top class.
    if ml_probs.get(ml_top, 0.0) >= 0.90:
        return ml_top, meta

    scores = {t: 0.4 * ml_probs.get(t, 0.0) for t in settings.CARE_TYPES}
    if llm["care_type"] in scores:
        scores[llm["care_type"]] += 0.6 * llm["confidence"]
    chosen = max(scores, key=scores.get)
    meta["used"] = "weighted" if chosen != ml_top else "ml"
    return chosen, meta
