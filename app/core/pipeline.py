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


def run_triage_pipeline(
    request: TriageRequest,
    db: Session | None = None,
    debug: bool = False,
) -> TriageResponse:
    """
    Executes the triage pipeline with full diagnostic tracing adhering to the official labels:
    CARE_TYPES = ["paramedic_home_visit", "home_nursing", "lab_test_home", "teleconsultation", "emergency_112"]
    URGENCIES = ["emergency", "same_day", "scheduled"]
    """
    user_input = request.user_input
    history_dicts = [{"role": m.role, "text": m.text or m.content or ""} for m in request.conversation_history]
    history_turns = len(request.conversation_history) // 2

    reasons: list[str] = []

    # 1. Language detection & normalisation
    orig_text, norm_text, detected_lang = detect_and_normalise(user_input)
    lang = request.language if request.language != "auto" else detected_lang

    # 2. Red-flag check (only high-severity flags from the 9 official categories)
    high_flags, medium_flags, severity, is_high_emergency = check_red_flags(
        orig_text, norm_text, return_medium=True
    )

    if is_high_emergency:
        emergency_steps = _get_emergency_steps(lang)
        reasoning = build_reasoning(
            symptoms=[],
            duration=None,
            breathing_difficulty=True if "breathlessness" in high_flags else None,
            chest_pain=True if "chest_pain" in high_flags else None,
            red_flags=high_flags,
            care_type="emergency_112",
            urgency="emergency",
            modifiers=[],
            language=lang,
        )

        debug_trace = {
            "red_flags_high": high_flags,
            "red_flags_medium": medium_flags,
            "model_probs": {"emergency_112": 1.0},
            "urgency_after_cost_matrix": "emergency",
            "urgency_after_risk_modifiers": "emergency",
            "urgency_after_confidence_fallback": "emergency",
            "confidence": 1.0,
            "slots": {},
            "final_care_type": "emergency_112",
            "final_urgency": "emergency",
            "reasons": ["High-severity official red flag triggered immediate 112 emergency bypass"],
        }

        resp = TriageResponse(
            follow_up_question=None,
            follow_up_options=[],
            care_type="emergency_112",
            urgency="emergency",
            red_flags=high_flags,
            reasoning=reasoning,
            confidence=1.0,
            matched_caregivers=[],
            emergency_steps=emergency_steps,
            debug=debug_trace if debug else None,
        )

        if db:
            try:
                log = AuditLog(
                    user_input=user_input,
                    language=lang,
                    red_flags=high_flags,
                    probabilities={"emergency_112": 1.0},
                    care_type="emergency_112",
                    urgency="emergency",
                    confidence=1.0,
                    reasoning=reasoning,
                    debug_trace=debug_trace,
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
        debug_trace = {
            "red_flags_high": high_flags,
            "red_flags_medium": medium_flags,
            "model_probs": None,
            "urgency_after_cost_matrix": None,
            "urgency_after_risk_modifiers": None,
            "urgency_after_confidence_fallback": None,
            "confidence": None,
            "slots": slots,
            "final_care_type": None,
            "final_urgency": None,
            "reasons": ["Needs more info: asked follow-up question"],
        }
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
            debug=debug_trace if debug else None,
        )

    # Reconstruct substantive user text for ML classification if current text is a bare follow-up reply
    bare_replies = {"no", "nahi", "nahin", "na", "yes", "haan", "ha", "not sure", "pata nahi", "unsure"}
    substantive_tokens = [
        (m.get("text") or "").strip()
        for m in history_dicts
        if m.get("role") == "user" and (m.get("text") or "").strip().lower() not in bare_replies
    ]
    if norm_text.strip().lower() not in bare_replies and norm_text.strip():
        substantive_tokens.append(norm_text.strip())
    patient_text = " ".join(substantive_tokens) if substantive_tokens else norm_text

    # 5. Triage model prediction (predicts care_type; urgency derived from CARE_TO_URGENCY)
    care_type, urgency, probs, confidence = predict_triage(slots, patient_text)
    reasons.append(f"Stage 5 (Model Prediction): care_type={care_type}, urgency={urgency}, probs={probs}, conf={confidence}")

    # 6. Risk modifiers
    urgency_after_risk_modifiers, care_type, applied_modifiers = apply_risk_modifiers(
        request.patient, slots, urgency, care_type
    )
    reasons.append(f"Stage 6 (Risk Modifiers): urgency={urgency_after_risk_modifiers}, care_type={care_type}, applied={applied_modifiers}")

    # 7. Confidence fallback (Rule 2: low confidence returns follow_up_question with care_type=null and urgency=null)
    urgency_after_confidence_fallback = urgency_after_risk_modifiers
    if (
        urgency_after_risk_modifiers != "emergency"
        and care_type != "emergency_112"
        and confidence < settings.CONF_THRESHOLD
    ):
        if history_turns < settings.MAX_FOLLOWUPS:
            q_text, q_options = select_follow_up_question(slots, lang)
            debug_trace = {
                "red_flags_high": high_flags,
                "red_flags_medium": medium_flags,
                "model_probs": probs,
                "urgency_after_cost_matrix": urgency,
                "urgency_after_risk_modifiers": urgency_after_risk_modifiers,
                "urgency_after_confidence_fallback": None,
                "confidence": confidence,
                "slots": slots,
                "final_care_type": None,
                "final_urgency": None,
                "reasons": reasons + [f"Stage 7: Low confidence ({confidence:.2f} < {settings.CONF_THRESHOLD}), returning follow-up question."],
            }
            return TriageResponse(
                follow_up_question=q_text,
                follow_up_options=q_options,
                care_type=None,
                urgency=None,
                red_flags=[],
                reasoning=None,
                confidence=round(confidence, 2) if confidence else None,
                matched_caregivers=[],
                emergency_steps=[],
                debug=debug_trace if debug else None,
            )
        else:
            reasons.append(f"Stage 7: Low confidence ({confidence:.2f}), turns exhausted; proceeding with best prediction.")

    # 8. Check for emergency escalation (Rule 2)
    user_answered_yes_high = (
        slots.get("breathing_difficulty") is True
        or slots.get("chest_pain") is True
        or slots.get("consciousness") == "unconscious"
        or slots.get("bleeding") is True
    )
    model_p_emergency = probs.get("emergency_112", 0.0) if isinstance(probs, dict) else 0.0
    has_pregnancy_emergency = "pregnancy_acute_risk" in applied_modifiers

    is_emergency = is_high_emergency or user_answered_yes_high or (model_p_emergency >= 0.50) or has_pregnancy_emergency

    if is_emergency:
        final_care_type = "emergency_112"
        final_urgency = "emergency"
        emergency_steps = _get_emergency_steps(lang)
        matched_caregivers = []
        reasons.append("Stage 8 (Rule 2): Emergency triggered -> emergency_112 & emergency")
    else:
        # Non-emergency
        final_care_type = care_type
        if final_care_type == "emergency_112":
            final_care_type = "paramedic_home_visit" if ("fever" in slots.get("symptoms", [])) else "teleconsultation"

        final_urgency = settings.CARE_TO_URGENCY.get(final_care_type, "same_day")
        emergency_steps = []
        matched_caregivers = rank_caregivers(
            care_type=final_care_type,
            urgency=final_urgency,
            user_location=request.location,
            user_language=lang,
            user_text=user_input,
            limit=3,
        )
        reasons.append(f"Stage 8: Non-emergency routing: care_type={final_care_type}, urgency={final_urgency}")

    # 9. Explainability
    reasoning = build_reasoning(
        symptoms=slots.get("symptoms", []),
        duration=slots.get("duration"),
        breathing_difficulty=slots.get("breathing_difficulty"),
        chest_pain=slots.get("chest_pain"),
        red_flags=high_flags,
        care_type=final_care_type,
        urgency=final_urgency,
        modifiers=applied_modifiers,
        language=lang,
    )

    debug_trace = {
        "red_flags_high": high_flags,
        "red_flags_medium": medium_flags,
        "model_probs": probs,
        "urgency_after_cost_matrix": urgency,
        "urgency_after_risk_modifiers": urgency_after_risk_modifiers,
        "urgency_after_confidence_fallback": urgency_after_confidence_fallback,
        "confidence": confidence,
        "slots": slots,
        "final_care_type": final_care_type,
        "final_urgency": final_urgency,
        "reasons": reasons,
    }

    # 10. Audit Log
    if db:
        try:
            log = AuditLog(
                user_input=user_input,
                language=lang,
                red_flags=high_flags,
                probabilities=probs,
                care_type=final_care_type,
                urgency=final_urgency,
                confidence=confidence,
                reasoning=reasoning,
                debug_trace=debug_trace,
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    return TriageResponse(
        follow_up_question=None,
        follow_up_options=[],
        care_type=final_care_type,
        urgency=final_urgency,
        red_flags=high_flags,
        reasoning=reasoning,
        confidence=round(confidence, 2) if confidence else None,
        matched_caregivers=matched_caregivers,
        emergency_steps=emergency_steps,
        debug=debug_trace if debug else None,
    )
