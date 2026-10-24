"""LLM second opinion (ML-first architecture).

The LLM runs in parallel AFTER the ML models have decided care_type and red
flags. It returns its own care_type, red flags and a one-line reason (strict
JSON; every evidence_quote must be a real substring of the message, else the
field is dropped). The LLM can only RAISE severity:

  - agree         -> the caller bumps confidence ("Second opinion: agrees")
  - more severe   -> the caller asks ONE confirmation question, never decides
  - less severe   -> ignored (the LLM can never lower urgency or remove a flag)

When LLM_ROLE=off or the call fails, the ML result stands unchanged.
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.core.language import normalise_text
from app.core.llm import llm_json, is_llm_available

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a second-opinion medical triage reviewer for an Indian home-care app. "
    "You review a decision that a machine-learning model already made and give your "
    "own independent read of the patient message.\n"
    "Official care types: paramedic_home_visit, home_nursing, lab_test_home, "
    "teleconsultation, emergency_112.\n"
    "Official red flags: chest_pain, breathlessness, unconsciousness, severe_bleeding, "
    "stroke_symptoms, seizure, high_fever_infant, suicidal_ideation, severe_dehydration.\n"
    "Rules:\n"
    "- Only report a red flag that is actually PRESENT in the message.\n"
    "- For each flag you report, give an evidence_quote that is an EXACT substring of "
    "the message (empty string if none).\n"
    "- reason: one short line (<= 15 words) explaining your care_type.\n"
    "Return JSON: {\"care_type\": ..., \"red_flags\": [...], \"reason\": ..., "
    "\"evidence_quotes\": {\"flag\": \"quote\"}}."
)


class SecondOpinionOut(BaseModel):
    care_type: str = ""
    red_flags: list[str] = Field(default_factory=list)
    reason: str = ""
    evidence_quotes: dict[str, str] = Field(default_factory=dict)


def _quote_is_evidence(quote: str, text: str) -> bool:
    if not quote or not quote.strip():
        return False
    q = normalise_text(quote)
    t = normalise_text(text)
    return len(q) >= 4 and q in t


def _validated_flags(out: SecondOpinionOut, text: str) -> list[str]:
    """Keep only flags that (a) are official and (b) have an evidence quote that
    is a real substring of the message."""
    flags: list[str] = []
    seen: set[str] = set()
    for flag in out.red_flags or []:
        flag = (flag or "").strip()
        if flag not in settings.RED_FLAGS or flag in seen:
            continue
        seen.add(flag)
        quote = (out.evidence_quotes or {}).get(flag, "")
        if quote and not _quote_is_evidence(quote, text):
            continue
        flags.append(flag)
    return flags


def run_second_opinion(text: str, lang: str = "en") -> Optional[dict]:
    """Returns {"care_type", "red_flags", "reason"} or None when disabled/failed."""
    if settings.LLM_ROLE == "off" or not is_llm_available():
        return None
    try:
        out = llm_json(
            system=SYSTEM_PROMPT,
            user=f"Patient message: \"{text}\"",
            schema=SecondOpinionOut,
            model=settings.DEEPSEEK_MODEL,
            timeout=settings.SCREEN_TIMEOUT_S,
            retries=1,
        )
        if out is None:
            return None
        care_type = out.care_type.strip() if out.care_type else ""
        if care_type not in settings.CARE_TYPES:
            care_type = ""
        flags = _validated_flags(out, text)
        return {
            "care_type": care_type,
            "red_flags": flags,
            "reason": (out.reason or "").strip(),
        }
    except Exception as e:
        logger.warning(f"Second opinion LLM call failed: {e}")
        return None


_CARE_SEVERITY = {
    "emergency_112": 4,
    "paramedic_home_visit": 3,
    "home_nursing": 3,
    "teleconsultation": 2,
    "lab_test_home": 1,
    "": 0,
}


def reconcile(ml_care_type: str, ml_flags: list[str], llm: Optional[dict]) -> dict:
    """Reconciles the ML decision with the LLM second opinion.

    Returns a dict:
      {"agrees": bool, "llm_care_type": str|None, "note": str, "ask": bool,
       "ask_flags": [str]}
    The LLM can never lower urgency or remove a red flag; a more-severe LLM
    opinion only asks a confirmation question (never decides).
    """
    if llm is None:
        return {"agrees": False, "llm_care_type": None, "note": "llm_unavailable", "ask": False, "ask_flags": []}

    llm_care_type = llm.get("care_type") or ""
    llm_flags = [f for f in (llm.get("red_flags") or []) if f in settings.RED_FLAGS]
    ml_flags = list(ml_flags or [])
    ml_is_emergency = ml_care_type == "emergency_112"
    llm_is_emergency = llm_care_type == "emergency_112"

    new_flags = [f for f in llm_flags if f not in ml_flags]

    # Agree: same care_type (or both non-emergency service-level) and no new flags.
    if llm_care_type == ml_care_type and not new_flags:
        return {"agrees": True, "llm_care_type": llm_care_type, "note": "agrees", "ask": False, "ask_flags": []}

    # More severe: LLM says emergency when ML did not, OR LLM found a flag the
    # rules/ML missed -> ask ONE confirmation question, never decide.
    if (llm_is_emergency and not ml_is_emergency) or new_flags:
        return {
            "agrees": False,
            "llm_care_type": llm_care_type,
            "note": "more_severe",
            "ask": True,
            "ask_flags": new_flags,
        }

    # Less severe: LLM would downgrade -> ignore.
    return {"agrees": False, "llm_care_type": llm_care_type, "note": "less_severe_ignored", "ask": False, "ask_flags": []}
