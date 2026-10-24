import logging
from typing import Any
import yaml
try:
    from sqlalchemy.orm import Session
except ImportError:
    Session = Any
from app.config import settings
from app.schemas import (
    TriageRequest,
    TriageResponse,
    MatchedCaregiver,
)
from app.core.language import detect_and_normalise
from app.core.red_flags import check_red_flags
from app.core.intake import extract_slots, needs_more_info, select_follow_up_question
from app.core.triage_model import predict_triage
from app.core.risk_modifiers import apply_risk_modifiers
from app.core.matching import rank_caregivers
from app.core.explain import build_reasoning
from app.db.models import AuditLog

logger = logging.getLogger(__name__)


def _get_emergency_steps(lang: str) -> list[str]:
    steps_file = settings.EMERGENCY_STEPS_FILE
    if steps_file.exists():
        try:
            with open(steps_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if lang in data:
                    return data[lang].get("steps", [])
                elif "en" in data:
                    return data["en"].get("steps", [])
        except Exception:
            pass
    return [
        "Call 112 (National Emergency) or 102 (Ambulance) immediately.",
        "Keep the patient sitting upright and calm.",
        "Do not offer solid foods, water, or unprescribed medicines.",
        "Unlock the door for the medical response team.",
    ]


def run_triage_pipeline(request: TriageRequest, db: Session | None = None) -> TriageResponse:
    """
    Executes the triage pipeline matching the Android app API contract.
    """
    user_input = request.user_input
    history_dicts = [{"role": m.role, "text": m.text} for m in request.conversation_history]
    history_turns = len(request.conversation_history) // 2

    # 1. Language detection & normalisation
    orig_text, norm_text, detected_lang = detect_and_normalise(user_input)
    lang = request.language if request.language != "auto" else detected_lang

    # 2. Red-flag check (only high-severity flags go into high_flags)
    high_flags, medium_flags, severity, is_high_emergency = check_red_flags(
        orig_text, norm_text, return_medium=True
    )

    if is_high_emergency:
        emergency_steps = _get_emergency_steps(lang)
        reasoning = build_reasoning(
            symptoms=[],
            duration=None,
            breathing_difficulty=True if "severe_breathlessness" in high_flags else None,
            chest_pain=True if "chest_pain" in high_flags else None,
            red_flags=high_flags,
            care_type="emergency_referral",
            urgency="immediate",
            modifiers=[],
            language=lang,
        )

        resp = TriageResponse(
            follow_up_question=None,
            follow_up_options=[],
            care_type="emergency_referral",
            urgency="immediate",
            red_flags=high_flags,
            reasoning=reasoning,
            confidence=1.0,
            matched_caregivers=[],
            emergency_steps=emergency_steps,
        )

        # Audit Log
        if db:
            try:
                log = AuditLog(
                    user_input=user_input,
                    language=lang,
                    red_flags=high_flags,
                    probabilities={"immediate": 1.0},
                    care_type="emergency_referral",
                    urgency="immediate",
                    confidence=1.0,
                    reasoning=reasoning,
                )
                db.add(log)
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to write audit log: {e}")

        return resp

    # 3. Intake slot extraction
    slots = extract_slots(norm_text, history_dicts)
    if medium_flags:
        slots["medium_red_flags"] = medium_flags

    # 4. Check if follow-up question is needed
    if needs_more_info(slots, history_turns) and history_turns < settings.MAX_FOLLOWUPS:
        q_text, q_options = select_follow_up_question(slots, lang)
        return TriageResponse(
            follow_up_question=q_text,
            follow_up_options=q_options,
            care_type=None,
            urgency=None,
            red_flags=[],
            reasoning=None,
            confidence=None,
            matched_caregivers=[],
            emergency_steps=[],
        )

    # 5. Triage model prediction
    care_type, urgency, probs, confidence = predict_triage(slots, norm_text)

    # 6. Risk modifiers
    urgency, care_type, applied_modifiers = apply_risk_modifiers(
        request.patient, slots, urgency, care_type
    )

    # Apply medium-severity red flags internally as risk modifier
    if medium_flags:
        if "high_fever_infant" in medium_flags:
            if urgency == "routine":
                urgency = "same_day"
            applied_modifiers.append("infant_high_fever_observed")

    # 7. Confidence fallback
    if confidence < settings.CONF_THRESHOLD and urgency == "routine":
        urgency = "same_day"

    # 8. Check for emergency escalation
    # CHANGE 3: whenever urgency is "immediate", force care_type = "emergency_referral",
    # fill emergency_steps, and skip caregiver matching.
    if urgency == "immediate" or care_type == "emergency_referral" or (high_flags and len(high_flags) > 0):
        care_type = "emergency_referral"
        urgency = "immediate"
        emergency_steps = _get_emergency_steps(lang)
        matched_caregivers = []
    else:
        emergency_steps = []
        matched_caregivers = rank_caregivers(
            care_type=care_type,
            urgency=urgency,
            user_location=request.location,
            user_language=lang,
            limit=3,
        )

    # 9. Explainability
    reasoning = build_reasoning(
        symptoms=slots.get("symptoms", []),
        duration=slots.get("duration"),
        breathing_difficulty=slots.get("breathing_difficulty"),
        chest_pain=slots.get("chest_pain"),
        red_flags=high_flags,
        care_type=care_type,
        urgency=urgency,
        modifiers=applied_modifiers,
        language=lang,
    )
    if medium_flags and "infant_high_fever_observed" in applied_modifiers:
        reasoning += " High fever in infant requires close same-day clinical assessment."

    # 10. Audit Log
    if db:
        try:
            log = AuditLog(
                user_input=user_input,
                language=lang,
                red_flags=high_flags,
                probabilities=probs,
                care_type=care_type,
                urgency=urgency,
                confidence=confidence,
                reasoning=reasoning,
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    return TriageResponse(
        follow_up_question=None,
        follow_up_options=[],
        care_type=care_type,
        urgency=urgency,
        red_flags=high_flags,
        reasoning=reasoning,
        confidence=round(confidence, 2) if confidence else None,
        matched_caregivers=matched_caregivers,
        emergency_steps=emergency_steps,
    )
