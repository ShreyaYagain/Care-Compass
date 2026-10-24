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
from app.core.language import detect_and_normalise, normalise_text
from app.core.red_flags import check_red_flags
from app.core.pregnancy import check_pregnancy
from app.core.intake import (
    extract_slots,
    needs_more_info,
    select_follow_up_question,
    count_assistant_turns,
    enforce_question_bank,
    get_question_by_id,
    is_bank_question,
    get_asked_ids,
)
from app.core.semantic_screen import (
    screen_red_flags,
    flag_question_id,
    QUESTION_TO_FLAG,
    NOT_SURE_AS_YES,
)
from app.core.triage_model import predict_triage
from app.core.risk_modifiers import apply_risk_modifiers
from app.core.matching import rank_caregivers
from app.core.explain import build_reasoning
from app.core.context import get_context, season_display
from app.core.guardrails import (
    input_guard,
    output_guard,
    get_scope_refusal,
    get_disclaimer,
    get_escalation_line,
)
from app.db.models import AuditLog

logger = logging.getLogger(__name__)

_BARE_ANSWERS = {
    "no", "nahi", "nahin", "nahim", "n", "na",
    "yes", "haan", "ha", "han", "y", "ji haan",
    "not sure", "pata nahi", "unsure", "malum nahi", "pakka nahi",
    "nahi pata", "pata nahi hai", "not sure about", "sure nahi",
}


def _parse_semantic_answer(history_dicts: list[dict], user_input: str):
    """If the current message answers a semantic-screen confirmation question,
    return (flag, 'yes'|'no'|'unsure'), else None."""
    last_qid = None
    for m in reversed(history_dicts):
        if m.get("role") == "assistant":
            qid = is_bank_question(m.get("text") or m.get("content") or "")
            if qid and qid in QUESTION_TO_FLAG:
                last_qid = qid
            break
    if not last_qid:
        return None
    ans = (user_input or "").strip().lower()
    if ans in {"yes", "haan", "ha", "han", "y", "ji haan", "haan ji", "han ji"}:
        return QUESTION_TO_FLAG[last_qid], "yes"
    if ans in {"no", "nahi", "nahin", "nahim", "n", "na", "nhi"}:
        return QUESTION_TO_FLAG[last_qid], "no"
    if ans in {"not sure", "pata nahi", "unsure", "malum nahi", "pakka nahi", "nahi pata"}:
        return QUESTION_TO_FLAG[last_qid], "unsure"
    return None


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


def _context_summary_line(context: dict, lang: str) -> str:
    """One-line localised weather/time/location summary for the result text."""
    loc = context.get("location_name") or ""
    temp = context.get("temperature_c")
    aqi = context.get("aqi")
    season = season_display(context.get("season", ""))
    t_str = context.get("local_time_str") or ""

    temp_s = f"{round(temp)}°C" if temp is not None else ""
    aqi_s = f"AQI {round(aqi)}" if aqi is not None else ""
    facts = [f for f in (loc, temp_s, aqi_s) if f]
    facts_str = ", ".join(facts)

    if lang == "hi":
        base = f"अभी {facts_str} है" if facts else "स्थानीय मौसम उपलब्ध नहीं"
        extra = f", {season} मौसम, समय {t_str}" if (season or t_str) else ""
        return f"{base}{extra}।"
    if lang == "hinglish":
        base = f"Abhi {facts_str} hai" if facts else "Local weather available nahi hai"
        extra = f", {season} season, time {t_str}" if (season or t_str) else ""
        return f"{base}{extra}."
    base = f"Right now: {facts_str}" if facts else "Local weather is unavailable"
    extra = f", {season} season, {t_str}" if (season or t_str) else ""
    return f"{base}{extra}."


def run_triage_pipeline(
    request: TriageRequest,
    db: Session | None = None,
    debug: bool = False,
) -> TriageResponse:
    """
    Executes the triage pipeline with full diagnostic tracing adhering to the official labels:
    CARE_TYPES = ["paramedic_home_visit", "home_nursing", "lab_test_home", "teleconsultation", "emergency_112"]
    URGENCIES = ["emergency", "same_day", "scheduled"]
    Integrates clinical safety guardrails (input sanitization, PII masking, response policy enforcement).
    """
    user_input = request.user_input

    # 0. Input Guardrail: PII masking, prompt injection, off-topic & abusive detection
    input_guard_res = input_guard(user_input)
    cleaned_input = input_guard_res["cleaned_text"]

    output_violations: list[str] = []
    template_replaced: bool = False

    history_dicts = [{"role": m.role, "text": m.text or m.content or ""} for m in request.conversation_history]
    history_turns = count_assistant_turns(history_dicts)

    # Check if disclaimer has already been shown in this session
    history_texts = [
        (m.text or m.content or "").lower()
        for m in request.conversation_history
        if m.role == "assistant"
    ]
    disclaimer_shown = any(
        "not a doctor" in t or "डॉक्टर नहीं है" in t or "doctor nahi hai" in t
        for t in history_texts
    )
    include_disclaimer = not disclaimer_shown

    reasons: list[str] = []
    if input_guard_res["flags"]:
        reasons.append(f"Input guard flags: {input_guard_res['flags']}")

    context_used = None
    context_reason = None

    # Context resolution (safe & optional)
    context = None
    if request.context_consent:
        lat = request.location.lat if request.location else None
        lng = request.location.lng if request.location else None
        try:
            context = get_context(lat=lat, lng=lng, client_time_str=request.client_time)
            # Weather/time/location are always shown with the result (not only
            # when they change the decision). Escalation branches replace this.
            context_used = {
                "season": season_display(context.get("season", "")),
                "weather": f"{round(context['temperature_c'])}°C" if context.get("temperature_c") is not None else "",
                "aqi": context.get("aqi"),
                "location": context.get("location_name") or None,
                "time": context.get("local_time_str") or None,
                "tags": context.get("tags", []),
                "reason": "",
            }
            reasons.append(f"Context gathered: season={context.get('season')}, tags={context.get('tags')}, temp={context.get('temperature_c')}, loc={context.get('location_name')}")
        except Exception as e:
            logger.warning(f"Failed to gather context: {e}")
            context = None

    # 1. Language detection & normalisation (performed on cleaned text)
    orig_text, norm_text, detected_lang = detect_and_normalise(cleaned_input)
    lang = request.language if request.language != "auto" else detected_lang

    # 2. Red-flag check (MUST run even if injection or off-topic is flagged)
    # Check both original and cleaned text so injection wrappers never hide true emergencies
    high_flags_orig, _, _, is_high_orig = check_red_flags(user_input, detect_and_normalise(user_input)[1], return_medium=True)
    high_flags_clean, medium_flags, severity, is_high_clean = check_red_flags(orig_text, norm_text, return_medium=True)

    high_flags = list(set(high_flags_orig + high_flags_clean))
    is_high_emergency = is_high_orig or is_high_clean

    # 2.1 Sticky red flags: rebuild flags from the WHOLE conversation on every
    # turn so an earlier emergency can never be lowered by a later answer
    # (e.g. turn 1 "dad cant breath", turn 2 "old person").
    history_user_texts = [
        (m.text or m.content or "") for m in request.conversation_history if m.role == "user"
    ]
    history_text = " . ".join(t.strip() for t in history_user_texts if t.strip())
    if history_text:
        high_flags_hist, medium_hist, _, is_high_hist = check_red_flags(
            history_text, normalise_text(history_text), return_medium=True
        )
        high_flags = list(set(high_flags + high_flags_hist))
        medium_flags = list(set(medium_flags + medium_hist))
        is_high_emergency = is_high_emergency or is_high_hist

    # 2.2 Deterministic pregnancy risk layer (before the LLM and the classifier).
    preg_input = f"{user_input} . {history_text}" if history_text else user_input
    pregnancy_risk = check_pregnancy(preg_input)
    if pregnancy_risk.emergency_flags or pregnancy_risk.force_emergency:
        high_flags = list(set(high_flags + pregnancy_risk.emergency_flags))
        is_high_emergency = True
    if pregnancy_risk.is_pregnant and pregnancy_risk.reason:
        reasons.append(f"Pregnancy layer: {pregnancy_risk.reason}")

    # 2.3 Semantic-screen confirmation answer: Yes (or Not-sure for the 7
    # critical flags) escalates; No continues. Never lowers rule decisions.
    semantic_answer = _parse_semantic_answer(history_dicts, user_input)
    if semantic_answer:
        s_flag, s_kind = semantic_answer
        if s_kind == "yes" or (s_kind == "unsure" and s_flag in NOT_SURE_AS_YES):
            high_flags = list(set(high_flags + [s_flag]))
            is_high_emergency = True
            reasons.append(f"Semantic screen: user confirmed red flag {s_flag} (answer={s_kind})")
        else:
            reasons.append(f"Semantic screen: user cleared red flag {s_flag} (answer={s_kind})")

    # Emergency branch (Immediate 112)
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
            include_disclaimer=include_disclaimer,
        )

        guard_res = output_guard(reasoning, lang=lang, is_emergency=True, care_type="emergency_112", field_name="reasoning")
        if not guard_res["ok"]:
            output_violations.extend(guard_res["violations"])
            template_replaced = True
        reasoning = guard_res["safe_text"]

        debug_trace = {
            "red_flags_high": high_flags,
            "red_flags_medium": medium_flags,
            "model_probs": {"emergency_112": 1.0},
            "calibrated_probabilities": {"emergency_112": 1.0},
            "urgency_after_cost_matrix": "emergency",
            "urgency_after_risk_modifiers": "emergency",
            "urgency_after_confidence_fallback": "emergency",
            "confidence": 1.0,
            "slots": {},
            "final_care_type": "emergency_112",
            "final_urgency": "emergency",
            "context_info": context,
            "guardrails": {
                "input_guard": input_guard_res,
                "output_violations": output_violations,
                "template_replaced": template_replaced,
            },
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
            context_used=None,
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

    # If NO emergency was triggered, but input was disallowed (prompt injection / off-topic / abusive)
    if not input_guard_res["allowed"]:
        refusal_text = get_scope_refusal(lang)
        redirect_options = {
            "hi": ["बुखार या खांसी", "दर्द या चोट", "कमज़ोर या बुज़ुर्ग व्यक्ति", "घाव / इंजेक्शन / पट्टी", "खून या लैब टेस्ट", "कुछ और"],
            "hinglish": ["Bukhar ya khansi", "Dard ya chot", "Kamzor ya buzurg person", "Ghaav / injection / dressing", "Lab test", "Kuch aur"],
            "en": ["Fever or cough", "Pain or injury", "Weak or elderly person", "Wound / injection / dressing", "Lab test", "Something else"],
        }.get(lang, ["Fever or cough", "Pain or injury", "Weak or elderly person", "Wound / injection / dressing", "Lab test", "Something else"])

        debug_trace = {
            "red_flags_high": [],
            "red_flags_medium": [],
            "model_probs": None,
            "calibrated_probabilities": None,
            "urgency_after_cost_matrix": None,
            "urgency_after_risk_modifiers": None,
            "urgency_after_confidence_fallback": None,
            "confidence": 0.0,
            "slots": {},
            "final_care_type": None,
            "final_urgency": None,
            "context_info": context,
            "guardrails": {
                "input_guard": input_guard_res,
                "output_violations": [],
                "template_replaced": False,
            },
            "reasons": [f"Input guard blocked input: {input_guard_res['reason']}"],
        }

        resp = TriageResponse(
            follow_up_question=refusal_text,
            follow_up_options=redirect_options,
            care_type=None,
            urgency=None,
            red_flags=[],
            reasoning=refusal_text,
            confidence=0.0,
            matched_caregivers=[],
            emergency_steps=[],
            context_used=None,
            debug=debug_trace if debug else None,
        )
        if db:
            try:
                log = AuditLog(
                    user_input=user_input,
                    language=lang,
                    red_flags=[],
                    probabilities=None,
                    care_type=None,
                    urgency=None,
                    confidence=0.0,
                    reasoning=refusal_text,
                    debug_trace=debug_trace,
                )
                db.add(log)
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to write audit log: {e}")
        return resp

    # 2.4 SEMANTIC RED-FLAG SCREEN (after keyword rules, before follow-ups and
    # the classifier). Meaning-based detection; a present flag becomes ONE
    # confirmation question — the LLM never decides an emergency by itself.
    semantic_flags: list[str] = []
    if user_input.strip().lower() not in _BARE_ANSWERS:
        try:
            semantic_flags = screen_red_flags(user_input, lang)
        except Exception as e:
            logger.warning(f"Semantic red-flag screen failed: {e}")
            semantic_flags = []
    if semantic_flags:
        asked_ids = get_asked_ids(history_dicts)
        for s_flag in semantic_flags:
            qid = flag_question_id(s_flag)
            if qid and qid not in asked_ids:
                q_text, q_options = get_question_by_id(qid, lang)
                q_text = enforce_question_bank(q_text, lang)
                guard_q = output_guard(q_text, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_question")
                if not guard_q["ok"]:
                    output_violations.extend(guard_q["violations"])
                    template_replaced = True
                q_text = guard_q["safe_text"]

                debug_trace = {
                    "red_flags_high": high_flags,
                    "red_flags_medium": medium_flags,
                    "model_probs": None,
                    "calibrated_probabilities": None,
                    "urgency_after_cost_matrix": None,
                    "urgency_after_risk_modifiers": None,
                    "urgency_after_confidence_fallback": None,
                    "confidence": None,
                    "slots": {},
                    "final_care_type": None,
                    "final_urgency": None,
                    "context_info": context,
                    "semantic_screen": {"flags": semantic_flags, "asked": qid},
                    "guardrails": {
                        "input_guard": input_guard_res,
                        "output_violations": output_violations,
                        "template_replaced": template_replaced,
                    },
                    "reasons": [f"Semantic screen detected candidate red flag(s) {semantic_flags}; asking confirmation ({qid})"],
                }
                resp = TriageResponse(
                    follow_up_question=q_text,
                    follow_up_options=q_options,
                    care_type=None,
                    urgency=None,
                    red_flags=[],
                    reasoning=None,
                    confidence=None,
                    matched_caregivers=[],
                    emergency_steps=[],
                    context_used=None,
                    debug=debug_trace if debug else None,
                )
                if db:
                    try:
                        log = AuditLog(
                            user_input=user_input,
                            language=lang,
                            red_flags=[],
                            probabilities=None,
                            care_type=None,
                            urgency=None,
                            confidence=None,
                            reasoning=None,
                            debug_trace=debug_trace,
                        )
                        db.add(log)
                        db.commit()
                    except Exception as e:
                        logger.warning(f"Failed to write audit log: {e}")
                return resp

    # 3. Intake slot extraction (on sanitized text)
    slots = extract_slots(norm_text, history_dicts)
    if medium_flags:
        slots["medium_red_flags"] = medium_flags

    # 3.1 Merge the deterministic pregnancy layer result into slots so the
    # follow-up policy and the risk modifiers can act on it.
    if pregnancy_risk.is_pregnant:
        slots["pregnancy"] = True
        if pregnancy_risk.reason:
            slots["pregnancy_reason"] = pregnancy_risk.reason

    # 4. Check if follow-up question is needed
    if needs_more_info(slots, history_turns, history_dicts):
        q_text, q_options = select_follow_up_question(slots, lang, history_dicts, context)
        q_text = enforce_question_bank(q_text, lang)

        # Output guard on follow up question and options
        guard_q = output_guard(q_text, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_question")
        if not guard_q["ok"]:
            output_violations.extend(guard_q["violations"])
            template_replaced = True
        q_text = guard_q["safe_text"]

        safe_opts = []
        for opt in q_options:
            guard_opt = output_guard(opt, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_options")
            if not guard_opt["ok"]:
                output_violations.extend(guard_opt["violations"])
                template_replaced = True
            safe_opts.append(guard_opt["safe_text"])
        q_options = safe_opts

        # If context inspired follow-up
        if context and any(t in ["monsoon_season", "poor_air"] for t in context.get("tags", [])):
            if "joint pain" in q_text.lower() or "vector" in q_text.lower():
                context_used = {
                    "season": context.get("season"),
                    "weather": f"{round(context['temperature_c'])}°C" if context.get("temperature_c") else "",
                    "aqi": context.get("aqi"),
                    "tags": context.get("tags", []),
                    "reason": "Monsoon season flagged screening for vector-borne viral illnesses",
                }

        debug_trace = {
            "red_flags_high": high_flags,
            "red_flags_medium": medium_flags,
            "model_probs": None,
            "calibrated_probabilities": None,
            "urgency_after_cost_matrix": None,
            "urgency_after_risk_modifiers": None,
            "urgency_after_confidence_fallback": None,
            "confidence": None,
            "slots": slots,
            "final_care_type": None,
            "final_urgency": None,
            "context_info": context,
            "guardrails": {
                "input_guard": input_guard_res,
                "output_violations": output_violations,
                "template_replaced": template_replaced,
            },
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
            context_used=context_used,
            debug=debug_trace if debug else None,
        )

    # Reconstruct substantive user text for ML classification if current text is a bare reply
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
    pred_res = predict_triage(slots, patient_text)
    if len(pred_res) == 6:
        care_type, urgency, probs, confidence, top_terms, nearest_examples = pred_res
    else:
        care_type, urgency, probs, confidence = pred_res[:4]
        top_terms, nearest_examples = [], []

    reasons.append(f"Stage 5 (Model Prediction): care_type={care_type}, urgency={urgency}, probs={probs}, conf={confidence}")

    # Out-of-dataset mapping from LLM if model has low confidence
    if slots.get("unfamiliar_care_type_mapped") and confidence < 0.65:
        mapped_type = slots["unfamiliar_care_type_mapped"]
        if mapped_type in settings.CARE_TYPES and mapped_type != "emergency_112":
            care_type = mapped_type
            urgency = settings.CARE_TO_URGENCY.get(care_type, "same_day")
            reasons.append(f"Stage 5 (Unfamiliar request mapped): care_type={care_type} ({slots.get('unfamiliar_reason')})")

    # 6. Risk modifiers
    urgency_after_risk_modifiers, care_type, applied_modifiers = apply_risk_modifiers(
        request.patient, slots, urgency, care_type
    )
    reasons.append(f"Stage 6 (Risk Modifiers): urgency={urgency_after_risk_modifiers}, care_type={care_type}, applied={applied_modifiers}")

    # 7. Confidence fallback & Max follow-ups decision rule
    urgency_after_confidence_fallback = urgency_after_risk_modifiers
    unclear_fallback = False

    has_specific_symptoms = any(
        s in slots.get("symptoms", [])
        for s in ["fever", "cough", "chest_pain", "breathlessness", "headache", "stomach_pain", "joint_pain", "nursing_procedure", "lab_test"]
    )
    is_unclear = (confidence < settings.CONF_THRESHOLD) or (not has_specific_symptoms and slots.get("service_requested") in ["none", "doctor"])

    if history_turns >= settings.MAX_FOLLOWUPS:
        if is_unclear and urgency_after_risk_modifiers != "emergency" and care_type != "emergency_112":
            care_type = "teleconsultation"
            urgency_after_confidence_fallback = "same_day"
            unclear_fallback = True
            reasons.append(f"Stage 7: Max follow-ups reached ({history_turns} turns); condition unclear. Defaulted to teleconsultation as safest first step.")
    elif (
        urgency_after_risk_modifiers != "emergency"
        and care_type != "emergency_112"
        and confidence < settings.CONF_THRESHOLD
    ):
        if needs_more_info(slots, history_turns, history_dicts):
            q_text, q_options = select_follow_up_question(slots, lang, history_dicts, context)
            q_text = enforce_question_bank(q_text, lang)

            guard_q = output_guard(q_text, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_question")
            if not guard_q["ok"]:
                output_violations.extend(guard_q["violations"])
                template_replaced = True
            q_text = guard_q["safe_text"]

            safe_opts = []
            for opt in q_options:
                guard_opt = output_guard(opt, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_options")
                if not guard_opt["ok"]:
                    output_violations.extend(guard_opt["violations"])
                    template_replaced = True
                safe_opts.append(guard_opt["safe_text"])
            q_options = safe_opts

            debug_trace = {
                "red_flags_high": high_flags,
                "red_flags_medium": medium_flags,
                "model_probs": probs,
                "calibrated_probabilities": probs,
                "urgency_after_cost_matrix": urgency,
                "urgency_after_risk_modifiers": urgency_after_risk_modifiers,
                "urgency_after_confidence_fallback": None,
                "confidence": confidence,
                "slots": slots,
                "final_care_type": None,
                "final_urgency": None,
                "context_info": context,
                "guardrails": {
                    "input_guard": input_guard_res,
                    "output_violations": output_violations,
                    "template_replaced": template_replaced,
                },
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
                context_used=None,
                debug=debug_trace if debug else None,
            )
        else:
            reasons.append(f"Stage 7: Low confidence ({confidence:.2f}); proceeding with best prediction without service asking.")

    # 8. Emergency check (Rule 2)
    user_answered_yes_high = (
        slots.get("breathing_difficulty") is True
        or slots.get("chest_pain") is True
        or slots.get("consciousness") == "unconscious"
        or slots.get("bleeding") is True
    )
    model_p_emergency = probs.get("emergency_112", 0.0) if isinstance(probs, dict) else 0.0
    has_pregnancy_emergency = "pregnancy_acute_risk" in applied_modifiers

    has_red_flag_signal = bool(
        high_flags
        or medium_flags
        or slots.get("breathing_difficulty") is True
        or slots.get("chest_pain") is True
        or slots.get("consciousness") in ["unconscious", "drowsy"]
        or slots.get("bleeding") is True
        or slots.get("severity") == "severe"
    )

    is_emergency = is_high_emergency or user_answered_yes_high or (model_p_emergency >= 0.50 and has_red_flag_signal) or has_pregnancy_emergency

    # Context Escalations
    if not is_emergency and context:
        tags = context.get("tags", [])
        temp_c = context.get("temperature_c")
        aqi_val = context.get("aqi")
        is_senior = (
            slots.get("age_group") == "senior"
            or slots.get("patient_relation") in ["grandmother", "grandfather", "senior", "dada", "dadi"]
            or (request.patient and request.patient.age and request.patient.age >= 65)
        )
        patient_conds = (
            getattr(request.patient, "conditions", None)
            or getattr(request.patient, "chronic_conditions", None)
            or []
        )
        has_asthma = "asthma" in slots.get("chronic_conditions", []) or "asthma" in patient_conds

        if ("heat_wave" in tags or (temp_c is not None and temp_c >= 40.0)) and is_senior:
            if any(s in slots.get("symptoms", []) for s in ["fever", "restlessness", "headache", "dizziness"]):
                is_emergency = True
                context_reason = f"Given the extreme heat wave ({round(temp_c) if temp_c is not None else 40}°C) and patient's senior age, fever/discomfort requires urgent medical stabilization."
                context_used = {
                    "season": season_display(context.get("season", "")),
                    "weather": f"{round(temp_c)}°C" if temp_c is not None else "Heat wave",
                    "aqi": aqi_val,
                    "location": context.get("location_name") or None,
                    "time": context.get("local_time_str") or None,
                    "tags": tags,
                    "reason": context_reason,
                }
                reasons.append("Context Escalation: Heat wave + senior + fever/restlessness escalated to emergency_112")

        if not is_emergency and ("poor_air" in tags or (aqi_val is not None and aqi_val >= 200)) and has_asthma:
            if any(s in slots.get("symptoms", []) for s in ["breathlessness", "cough", "saans"]):
                is_emergency = True
                context_reason = f"Hazardous air quality (AQI {round(aqi_val) if aqi_val else 200}) posing acute respiratory risk for known asthma."
                context_used = {
                    "season": season_display(context.get("season", "")),
                    "weather": context.get("summary", ""),
                    "aqi": aqi_val,
                    "location": context.get("location_name") or None,
                    "time": context.get("local_time_str") or None,
                    "tags": tags,
                    "reason": context_reason,
                }
                reasons.append("Context Escalation: Severe air pollution + asthma + respiratory symptom escalated to emergency_112")

    if is_emergency:
        final_care_type = "emergency_112"
        final_urgency = "emergency"
        emergency_steps = _get_emergency_steps(lang)
        matched_caregivers = []
        reasons.append("Stage 8 (Rule 2): Emergency triggered -> emergency_112 & emergency")
    else:
        final_care_type = care_type
        if final_care_type == "emergency_112":
            final_care_type = "paramedic_home_visit" if ("fever" in slots.get("symptoms", [])) else "teleconsultation"

        # Pregnancy floor: never "scheduled"; same_day teleconsultation at minimum.
        if slots.get("pregnancy"):
            if final_care_type == "lab_test_home":
                final_care_type = "teleconsultation"
                reasons.append("Pregnancy floor: lab test replaced by same_day teleconsultation.")

        final_urgency = settings.CARE_TO_URGENCY.get(final_care_type, "same_day")
        if slots.get("pregnancy") and final_urgency == "scheduled":
            final_urgency = "same_day"
            reasons.append("Pregnancy floor: urgency raised to same_day.")

        if (
            context
            and final_care_type == "paramedic_home_visit"
            and final_urgency == "same_day"
            and (context.get("is_night") or "rainy" in context.get("tags", []) or (context.get("precipitation_mm") or 0) >= 1.0)
            and not high_flags
            and slots.get("severity") != "severe"
            and slots.get("age_group") != "child"
        ):
            final_care_type = "teleconsultation"
            temp_val = round(context["temperature_c"]) if context.get("temperature_c") is not None else None
            precip = context.get("precipitation_mm") or 0
            is_rainy = "rainy" in context.get("tags", []) or precip >= 1.0
            if is_rainy:
                rain_part = f"rain ({precip} mm)" if precip else "rain"
                cond = f"Given {rain_part}" + (f" at {temp_val}°C" if temp_val is not None else "")
                weather_desc = f"{temp_val}°C rainy" if temp_val is not None else "Rainy"
            else:
                cond = "Given night-time" + (f" at {temp_val}°C" if temp_val is not None else "")
                weather_desc = f"{temp_val}°C night" if temp_val is not None else "Night-time"
            adj_reason = f"{cond}, we recommend an immediate virtual teleconsultation; a home visit can be dispatched in the morning if needed."
            context_reason = adj_reason
            context_used = {
                "season": season_display(context.get("season", "")),
                "weather": weather_desc,
                "aqi": context.get("aqi"),
                "location": context.get("location_name") or None,
                "time": context.get("local_time_str") or None,
                "tags": context.get("tags", []),
                "reason": adj_reason,
            }
            reasons.append("Context Soft Adjustment: Night/rain shifted paramedic_home_visit to immediate teleconsultation (same_day)")

        emergency_steps = []
        matched_caregivers = rank_caregivers(
            care_type=final_care_type,
            urgency=final_urgency,
            user_location=request.location,
            user_language=lang,
            user_text=cleaned_input,
            limit=3,
        )
        reasons.append(f"Stage 8: Non-emergency routing: care_type={final_care_type}, urgency={final_urgency}")

    # 9. Explainability & Guardrail Enforcement
    if unclear_fallback:
        unclear_msg = {
            "en": "We could not be sure what you need, so a doctor video consult is the safest first step.",
            "hinglish": "Hum samajh nahi paaye ki aapko kya chahiye, isliye doctor video consult sabse safe pehla kadam hai.",
            "hi": "हम समझ नहीं पाए कि आपको क्या चाहिए, इसलिए डॉक्टर वीडियो परामर्श सबसे सुरक्षित पहला कदम है।",
        }.get(lang, "We could not be sure what you need, so a doctor video consult is the safest first step.")
        escalation = get_escalation_line(lang)
        disclaimer = get_disclaimer(lang) if include_disclaimer else ""
        reasoning_parts = []
        if disclaimer:
            reasoning_parts.append(disclaimer)
        reasoning_parts.append(unclear_msg)
        reasoning_parts.append(escalation)
        reasoning = " ".join(reasoning_parts).strip()
    else:
        # Weather/time/location summary accompanies every result (when consent
        # was given). Escalations keep their own reason instead.
        context_summary = None
        if context and context_used is not None and not context_reason:
            context_summary = _context_summary_line(context, lang)
            context_used["reason"] = context_summary

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
            context_reason=context_reason,
            context_summary=context_summary,
            top_terms=top_terms,
            include_disclaimer=include_disclaimer,
        )

    guard_res = output_guard(reasoning, lang=lang, is_emergency=is_emergency, care_type=final_care_type, field_name="reasoning")
    if not guard_res["ok"]:
        output_violations.extend(guard_res["violations"])
        template_replaced = True
    reasoning = guard_res["safe_text"]

    # Output guard on matched caregiver reasons
    for cg in matched_caregivers:
        if cg.reason:
            cg_guard = output_guard(cg.reason, lang=lang, is_emergency=False, care_type=final_care_type, field_name="caregiver_reason")
            if not cg_guard["ok"]:
                output_violations.extend(cg_guard["violations"])
                template_replaced = True
            cg.reason = cg_guard["safe_text"]

    # Output guard on context reason
    if context_used and context_used.get("reason"):
        ctx_guard = output_guard(context_used["reason"], lang=lang, is_emergency=False, care_type=final_care_type, field_name="context_reason")
        if not ctx_guard["ok"]:
            output_violations.extend(ctx_guard["violations"])
            template_replaced = True
        context_used["reason"] = ctx_guard["safe_text"]

    debug_trace = {
        "red_flags_high": high_flags,
        "red_flags_medium": medium_flags,
        "model_probs": probs,
        "calibrated_probabilities": probs,
        "top_terms": top_terms,
        "nearest_examples": nearest_examples,
        "urgency_after_cost_matrix": urgency,
        "urgency_after_risk_modifiers": urgency_after_risk_modifiers,
        "urgency_after_confidence_fallback": urgency_after_confidence_fallback,
        "confidence": confidence,
        "slots": slots,
        "final_care_type": final_care_type,
        "final_urgency": final_urgency,
        "context_info": context,
        "guardrails": {
            "input_guard": input_guard_res,
            "output_violations": output_violations,
            "template_replaced": template_replaced,
        },
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
        context_used=context_used,
        debug=debug_trace if debug else None,
    )
