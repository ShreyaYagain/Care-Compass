import asyncio
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
    count_asked_id,
    build_classifier_text,
    _select_question_id,
)
from app.core.semantic_screen import (
    screen_red_flags,
    flag_question_id,
    QUESTION_TO_FLAG,
    NOT_SURE_AS_YES,
    COMBINED_QUESTION_ID,
    WHICH_ONE_QUESTION_ID,
    map_combined_category,
    _filter_unconsciousness_for_plain_headaches,
)
from app.core.redflag_model import predict_flags as ml_predict_flags
from app.core.second_opinion import run_second_opinion, reconcile as reconcile_second_opinion
from app.core.triage_model import predict_triage
from app.core.risk_modifiers import apply_risk_modifiers
from app.core.matching import rank_caregivers
from app.core.explain import build_reasoning, build_card_lines, card_text, context_line
from app.core.modules import (
    detect_module,
    llm_select_module,
    render_module_card,
    injury_decision,
    merge_answers_into_slots,
    module_next_question,
    MODULE_MAX_QUESTIONS,
    summarize_answers,
)
from app.core.synthetic import secondary_doctor_options, adjust_by_doctor_availability
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

_PICK_CLOSEST = {
    "en": "Pick the closest one or say \"talk to a doctor\".",
    "hinglish": "Sabse close option chuniye ya \"talk to a doctor\" boliye.",
    "hi": "सबसे करीबी विकल्प चुनें या \"डॉक्टर से बात करें\" कहें।",
}


def _pick_closest_line(lang: str) -> str:
    return _PICK_CLOSEST.get(lang, _PICK_CLOSEST["en"])


def _parse_semantic_answer(history_dicts: list[dict], user_input: str):
    """If the current message answers a semantic-screen question, return one of:
        ("flag_confirm", flag, kind)   per-flag confirmation answer
        ("combined", kind, flag)       combined failsafe answer (kind yes/no/unsure)
        ("which_one", flag)            which-one clarification answer
    else None."""
    last_qid = None
    for m in reversed(history_dicts):
        if m.get("role") == "assistant":
            qid = is_bank_question(m.get("text") or m.get("content") or "")
            if qid:
                last_qid = qid
            break
    if not last_qid:
        return None
    ans = (user_input or "").strip().lower()
    if last_qid == COMBINED_QUESTION_ID:
        if ans in {"yes", "haan", "ha", "han", "y", "ji haan", "haan ji", "han ji"}:
            return "combined", "yes", map_combined_category(user_input)
        if ans in {"no", "nahi", "nahin", "nahim", "n", "na", "nhi"}:
            return "combined", "no", None
        if ans in {"not sure", "pata nahi", "unsure", "malum nahi", "pakka nahi", "nahi pata"}:
            return "combined", "unsure", map_combined_category(user_input)
        # A non-bare answer that names one of the six categories counts as Yes.
        named = map_combined_category(user_input)
        if named:
            return "combined", "yes", named
        return None
    if last_qid == WHICH_ONE_QUESTION_ID:
        return "which_one", map_combined_category(user_input) or "unspecified_emergency"
    if last_qid in QUESTION_TO_FLAG:
        flag = QUESTION_TO_FLAG[last_qid]
        if ans in {"yes", "haan", "ha", "han", "y", "ji haan", "haan ji", "han ji"}:
            return "flag_confirm", flag, "yes"
        if ans in {"no", "nahi", "nahin", "nahim", "n", "na", "nhi"}:
            return "flag_confirm", flag, "no"
        if ans in {"not sure", "pata nahi", "unsure", "malum nahi", "pakka nahi", "nahi pata"}:
            return "flag_confirm", flag, "unsure"
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


def _injury_classifier(answers: dict, slots: dict):
    """Classifier view of an injury case for the calibrated P(emergency_112)
    gate: module answers folded into slots -> canonical classifier text."""
    merged = dict(slots)
    merge_answers_into_slots(merged, answers)
    return predict_triage(merged, build_classifier_text(merged))


def _apply_injury_sanity(care_type: str, urgency: str, slots: dict, patient) -> tuple[str, str]:
    """Sane routing for routine injury/joint pain outside the injury module.

    - home_nursing / lab_test misroutes for injuries -> teleconsultation
      (or paramedic_home_visit when severe).
    - paramedic_home_visit for mild-moderate, non-vulnerable pain -> 
      teleconsultation (a doctor video consult can decide if an X-ray is
      needed; a hospital does X-rays, not a home medic).
    Vulnerable patients (child/senior/pregnant/chronic/other-person) and
    severe pain keep the medic home visit."""
    symptoms = set(slots.get("symptoms") or [])
    if not (symptoms & {"injury", "joint_pain"}):
        return care_type, urgency
    vulnerable = (
        slots.get("age_group") in ("child", "senior")
        or slots.get("patient_relation") not in (None, "self", "")
        or slots.get("pregnancy")
        or slots.get("chronic_conditions")
        or (patient and patient.age and patient.age >= 60)
    )
    severe = slots.get("severity") == "severe"
    if care_type in ("home_nursing", "lab_test_home"):
        return ("paramedic_home_visit" if severe else "teleconsultation"), "same_day"
    if care_type == "paramedic_home_visit" and not vulnerable and not severe:
        return "teleconsultation", "same_day"
    return care_type, urgency


def _ask_next_module_question(module_id: str, answers: dict, slots: dict, lang: str, text: str):
    """The single next module question as a one-field card, or (None, None).

    Skips questions whose answer is already stated in the message (evidence)
    or filled from slots, so every card contains exactly ONE unanswered
    question and nothing is re-asked."""
    local_answers = dict(answers)
    while True:
        field_id = module_next_question(module_id, local_answers, slots)
        if not field_id:
            return None, None
        card = render_module_card(module_id, lang, slots, text, answered=local_answers, only_field=field_id)
        if card is not None:
            return field_id, card
        # Already answered in the message: mark it and move to the next question.
        local_answers[field_id] = "__stated__"


def _card_question_and_options(card: dict | None) -> tuple[str | None, list[str]]:
    """The full question text + tappable choices for a module card, so
    simpler clients can show something even without rendering the card.
    Never a bare symptom label."""
    fields = (card or {}).get("fields") or []
    if not fields:
        return None, []
    field = fields[0]
    question = field.get("question") or card.get("label") or ""
    options = field.get("options") or [] if field.get("type") != "slider010" else []
    return question or None, list(options)


def run_triage_pipeline(
    request: TriageRequest,
    db: Session | None = None,
    debug: bool = False,
    screen_result: dict | None = None,
    pre_slots: dict | None = None,
) -> TriageResponse:
    """
    Executes the triage pipeline with full diagnostic tracing adhering to the official labels:
    CARE_TYPES = ["paramedic_home_visit", "home_nursing", "lab_test_home", "teleconsultation", "emergency_112"]
    URGENCIES = ["emergency", "same_day", "scheduled"]
    Integrates clinical safety guardrails (input sanitization, PII masking, response policy enforcement).

    `screen_result` / `pre_slots` let the async wrapper (run_triage_pipeline_async)
    inject the semantic screen and intake extraction results it computed in
    parallel; both are recomputed here when omitted.
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
    context_key = None

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

    # 2.3 Semantic-screen answers. Per-flag confirmation: Yes (or Not-sure for
    # the critical flags) escalates; No continues. Combined failsafe: Yes / Not
    # sure -> emergency_112, using the specific flag the user named, or asking
    # ONE "which one" clarification (only when the combined question was the
    # first question, so the flow never exceeds two questions). Never lowers
    # rule decisions.
    semantic_answer = _parse_semantic_answer(history_dicts, user_input)
    if semantic_answer:
        kind = semantic_answer[0]
        if kind == "flag_confirm":
            _, s_flag, s_kind = semantic_answer
            if s_kind == "yes" or (s_kind == "unsure" and s_flag in NOT_SURE_AS_YES):
                high_flags = list(set(high_flags + [s_flag]))
                is_high_emergency = True
                reasons.append(f"Semantic screen: user confirmed red flag {s_flag} (answer={s_kind})")
            else:
                reasons.append(f"Semantic screen: user cleared red flag {s_flag} (answer={s_kind})")
        elif kind == "combined":
            _, c_kind, c_flag = semantic_answer
            if c_kind in ("yes", "unsure"):
                if c_flag:
                    high_flags = list(set(high_flags + [c_flag]))
                    is_high_emergency = True
                    reasons.append(f"Semantic screen: combined failsafe confirmed red flag {c_flag} (answer={c_kind})")
                elif c_kind == "yes" and history_turns == 1:
                    # Bare Yes with no named symptom and question budget left:
                    # ask which one (the second allowed question).
                    w_text, w_options = get_question_by_id(WHICH_ONE_QUESTION_ID, lang)
                    w_text = enforce_question_bank(w_text, lang)
                    guard_w = output_guard(w_text, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_question")
                    if not guard_w["ok"]:
                        output_violations.extend(guard_w["violations"])
                        template_replaced = True
                    w_text = guard_w["safe_text"]
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
                        "screen_status": "failsafe_question",
                        "semantic_screen": {"status": "failsafe_question", "flags": [], "combined": True, "asked": WHICH_ONE_QUESTION_ID},
                        "guardrails": {
                            "input_guard": input_guard_res,
                            "output_violations": output_violations,
                            "template_replaced": template_replaced,
                        },
                        "reasons": ["Combined failsafe answered Yes/Not sure; asking which symptom"],
                    }
                    return TriageResponse(
                        follow_up_question=w_text,
                        follow_up_options=w_options,
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
                else:
                    high_flags = list(set(high_flags + ["unspecified_emergency"]))
                    is_high_emergency = True
                    reasons.append(f"Semantic screen: combined failsafe confirmed (answer={c_kind}, symptom unnamed); escalating")
            else:
                reasons.append(f"Semantic screen: combined failsafe cleared (answer={c_kind})")
        elif kind == "which_one":
            w_flag = semantic_answer[1]
            high_flags = list(set(high_flags + [w_flag]))
            is_high_emergency = True
            reasons.append(f"Semantic screen: which-one answer mapped to red flag {w_flag}")

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
        )
        card_lines = build_card_lines(
            care_type="emergency_112",
            urgency="emergency",
            symptoms=[],
            duration=None,
            red_flags=high_flags,
            language=lang,
            chest_pain="chest_pain" in high_flags,
            breathing_difficulty="breathlessness" in high_flags,
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
            card_lines=card_lines,
            details={
                "symptoms": [],
                "answers": {},
                "context_used": None,
                "confidence": 1.0,
                "care_type": "emergency_112",
                "urgency": "emergency",
                "red_flags": high_flags,
            },
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
    # Skipped for bare answers and for the second follow-up answer
    # (history_turns >= MAX_FOLLOWUPS), and never runs when the rules already
    # decided emergency_112 (the emergency branch above returns earlier).
    screen_status = "skip"
    semantic_flags: list[str] = []
    combined_needed = False
    if user_input.strip().lower() not in _BARE_ANSWERS and history_turns < settings.MAX_FOLLOWUPS:
        try:
            if screen_result is None:
                screen_result = screen_red_flags(user_input, lang)
        except Exception as e:
            logger.warning(f"Semantic red-flag screen failed: {e}")
            screen_result = {"status": "skip", "flags": [], "combined": False}
    else:
        screen_result = {"status": "skip", "flags": [], "combined": False}
    screen_status = screen_result.get("status", "skip")
    semantic_flags = list(screen_result.get("flags") or [])
    combined_needed = bool(screen_result.get("combined"))

    # ML red-flag model (ML-first): decides together with the rules and the
    # screen. Its positive hits flow into the same single confirmation question.
    ml_red_flags: list[str] = []
    if user_input.strip().lower() not in _BARE_ANSWERS and history_turns < settings.MAX_FOLLOWUPS:
        try:
            ml_red_flags = ml_predict_flags(user_input)
            ml_red_flags = _filter_unconsciousness_for_plain_headaches(user_input, ml_red_flags)
            semantic_flags = list(set(semantic_flags + ml_red_flags))
        except Exception as e:
            logger.warning(f"ML red-flag model failed: {e}")

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
                    "screen_status": screen_status,
                    "semantic_screen": {"status": screen_status, "flags": semantic_flags, "combined": False, "asked": qid},
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

    # 2.4b Combined failsafe question: LLM down + local fallback empty + the
    # keyword rules found NO red flag + the message contains a symptom. Ask
    # ONE combined screening question from the closed bank — unless a red-flag
    # screening question was already answered this session. Never a silent
    # decision.
    if combined_needed:
        red_flag_screen_ids = set(QUESTION_TO_FLAG.keys()) | {COMBINED_QUESTION_ID}
        asked_ids = get_asked_ids(history_dicts)
        if not medium_flags and not any(qid in red_flag_screen_ids for qid in asked_ids):
            q_text, q_options = get_question_by_id(COMBINED_QUESTION_ID, lang)
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
                "screen_status": "failsafe_question",
                "semantic_screen": {"status": "failsafe_question", "flags": [], "combined": True, "asked": COMBINED_QUESTION_ID},
                "guardrails": {
                    "input_guard": input_guard_res,
                    "output_violations": output_violations,
                    "template_replaced": template_replaced,
                },
                "reasons": ["Semantic screen unavailable (LLM down after retry, local fallback empty); asking combined failsafe question"],
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
        else:
            reasons.append("Semantic screen failsafe skipped: red-flag screening already asked/answered this session")

    # 3. Intake slot extraction (on sanitized text)
    slots = pre_slots if pre_slots is not None else extract_slots(norm_text, history_dicts)
    if medium_flags:
        slots["medium_red_flags"] = medium_flags

    # 3.1 Merge the deterministic pregnancy layer result into slots so the
    # follow-up policy and the risk modifiers can act on it.
    if pregnancy_risk.is_pregnant:
        slots["pregnancy"] = True
        if pregnancy_risk.reason:
            slots["pregnancy_reason"] = pregnancy_risk.reason

    # 3.5 Symptom-specific follow-up MODULE (injury/fall, fever, abdominal, cough).
    # Follow-ups are asked ONE question per turn, at most MODULE_MAX_QUESTIONS;
    # the flow stops as soon as the case is determined.
    module_id = request.module_id or llm_select_module(norm_text, slots)

    if module_id and module_id == "injury" and request.module_answers is not None:
        next_field, next_card = _ask_next_module_question(module_id, request.module_answers, slots, lang, norm_text)
        if next_card is not None and history_turns < MODULE_MAX_QUESTIONS:
            card_q, card_opts = _card_question_and_options(next_card)
            guard_q = output_guard(card_q or next_card["label"], lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_question")
            safe_opts = [output_guard(o, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_options")["safe_text"] for o in card_opts]
            return TriageResponse(
                follow_up_question=guard_q["safe_text"], follow_up_options=safe_opts,
                care_type=None, urgency=None, red_flags=[], reasoning=None,
                matched_caregivers=[], emergency_steps=[], context_used=None,
                module_card=next_card,
                debug={"module_id": module_id, "module_answers": request.module_answers, "asked": next_field} if debug else None,
            )

        decision = injury_decision(request.module_answers, slots, classifier_fn=_injury_classifier)
        dc, du, df = decision["care_type"], decision["urgency"], decision["red_flags"]

        # Doctor availability (synthetic roster) may refine paramedic vs
        # teleconsultation when both are viable.
        avail_dc, avail_note = adjust_by_doctor_availability(dc, du, request.location, lang)
        ctx_key = None
        if avail_dc != dc:
            reasons.append(f"Availability routing: {dc} -> {avail_dc}")
            ctx_key = "no_home_doctor"
            dc = avail_dc

        meds = request.module_answers.get("meds_used")
        meds_line = f" You used: {meds}." if meds and str(meds) != "None" else ""
        module_reason = f"{decision['reason']}{meds_line}{avail_note}"

        why = summarize_answers(request.module_answers) or None
        lines = build_card_lines(
            care_type=dc, urgency=du, symptoms=slots.get("symptoms", []),
            duration=None, red_flags=df, language=lang,
            context_key=ctx_key, why_override=why,
        )
        details = {
            "symptoms": slots.get("symptoms", []),
            "answers": request.module_answers,
            "context_used": context_used,
            "confidence": 0.8 if dc != "emergency_112" else 1.0,
            "care_type": dc,
            "urgency": du,
            "red_flags": df,
        }

        if dc == "emergency_112":
            guard_res = output_guard(module_reason, lang=lang, is_emergency=True, care_type="emergency_112", field_name="reasoning")
            return TriageResponse(
                care_type="emergency_112", urgency="emergency", red_flags=df,
                reasoning=guard_res["safe_text"], emergency_steps=_get_emergency_steps(lang),
                matched_caregivers=[], context_used=context_used,
                debug={"module_id": module_id, "module_answers": request.module_answers} if debug else None,
                card_lines=lines, details=details,
            )

        matched = rank_caregivers(care_type=dc, urgency=du, user_location=request.location, user_language=lang, user_text=cleaned_input, limit=3)
        guard_res = output_guard(module_reason, lang=lang, is_emergency=False, care_type=dc, field_name="reasoning")
        return TriageResponse(
            care_type=dc, urgency=du, red_flags=df, reasoning=guard_res["safe_text"],
            confidence=0.8, matched_caregivers=matched, emergency_steps=[],
            context_used=context_used, secondary_options=secondary_doctor_options(dc, lang),
            debug={"module_id": module_id, "module_answers": request.module_answers} if debug else None,
            card_lines=lines, details=details,
        )

    if module_id and request.module_answers is not None and module_id != "injury":
        # Other modules: keep asking one question at a time (within the cap),
        # then fold all answers into slots and continue the normal flow.
        next_field, next_card = _ask_next_module_question(module_id, request.module_answers, slots, lang, norm_text)
        if next_card is not None and history_turns < MODULE_MAX_QUESTIONS:
            card_q, card_opts = _card_question_and_options(next_card)
            guard_q = output_guard(card_q or next_card["label"], lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_question")
            safe_opts = [output_guard(o, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_options")["safe_text"] for o in card_opts]
            return TriageResponse(
                follow_up_question=guard_q["safe_text"], follow_up_options=safe_opts,
                care_type=None, urgency=None, red_flags=[], reasoning=None,
                matched_caregivers=[], emergency_steps=[], context_used=None,
                module_card=next_card,
                debug={"module_id": module_id, "module_answers": request.module_answers, "asked": next_field} if debug else None,
            )
        merge_answers_into_slots(slots, request.module_answers)

    has_context = bool(
        slots.get("severity") or slots.get("duration") or slots.get("age_group")
        or slots.get("fever_temp") is not None
        or (slots.get("patient_relation") not in (None, "self", ""))
        or slots.get("pregnancy") or slots.get("chronic_conditions")
    )
    should_ask_module = module_id is not None and not is_high_emergency
    # Never ask a card when a red-flag answer (breathing/chest/consciousness/
    # bleeding) is already present in the conversation.
    if slots.get("breathing_difficulty") is True or slots.get("chest_pain") is True or \
            slots.get("consciousness") in ("unconscious", "drowsy") or slots.get("bleeding") is True:
        should_ask_module = False
    # Non-injury modules only ask when the case is still undecided: a single
    # symptom with no context. Multi-symptom / context -> decide directly.
    if should_ask_module and module_id != "injury" and (has_context or len(slots.get("symptoms", [])) >= 2):
        should_ask_module = False

    if should_ask_module and request.module_answers is None:
        next_field, card = _ask_next_module_question(module_id, {}, slots, lang, norm_text)
        if card is not None and history_turns < MODULE_MAX_QUESTIONS:
            card_q, card_opts = _card_question_and_options(card)
            guard_q = output_guard(card_q or card["label"], lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_question")
            safe_opts = [output_guard(o, lang=lang, is_emergency=False, care_type="teleconsultation", field_name="follow_up_options")["safe_text"] for o in card_opts]
            return TriageResponse(
                follow_up_question=guard_q["safe_text"], follow_up_options=safe_opts,
                care_type=None, urgency=None, red_flags=[], reasoning=None,
                matched_caregivers=[], emergency_steps=[], context_used=None,
                module_card=card,
                debug={"module_id": module_id, "slots": slots, "asked": next_field} if debug else None,
            )
        if module_id == "injury" and request.module_answers is None:
            # Nothing left to ask (all fields already stated): decide directly.
            decision = injury_decision({}, slots, classifier_fn=_injury_classifier)
            guard_res = output_guard(decision["reason"], lang=lang, is_emergency=decision["care_type"] == "emergency_112", care_type=decision["care_type"], field_name="reasoning")
            return TriageResponse(
                care_type=decision["care_type"], urgency=decision["urgency"], red_flags=decision["red_flags"],
                reasoning=guard_res["safe_text"],
                confidence=0.8 if decision["care_type"] != "emergency_112" else 1.0,
                matched_caregivers=rank_caregivers(care_type=decision["care_type"], urgency=decision["urgency"], user_location=request.location, user_language=lang, user_text=cleaned_input, limit=3) if decision["care_type"] != "emergency_112" else [],
                emergency_steps=_get_emergency_steps(lang) if decision["care_type"] == "emergency_112" else [],
                context_used=context_used,
                secondary_options=secondary_doctor_options(decision["care_type"], lang) if decision["care_type"] != "emergency_112" else [],
                debug={"module_id": module_id, "slots": slots} if debug else None,
            )

    # 4. Check if follow-up question is needed
    if needs_more_info(slots, history_turns, history_dicts):
        qid = _select_question_id(slots, history_dicts, context)
        q_text, q_options = select_follow_up_question(slots, lang, history_dicts, context)
        q_text = enforce_question_bank(q_text, lang)

        # Irrelevant input: the main-symptom bank question already says "no
        # symptoms were recognised". The second empty attempt adds a
        # "pick the closest" hint so the user has a clear way to proceed.
        if qid == "main_symptom_buttons" and count_asked_id(history_dicts, "main_symptom_buttons") >= 1:
            q_text = f"{q_text} {_pick_closest_line(lang)}"

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
            "screen_status": screen_status,
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

    # Classifier input is a cleaned string built from canonical symptom names and
    # validated slots — never the raw text — so random noise tokens cannot shift
    # the prediction. The raw text is preserved only in the audit log.
    patient_text = build_classifier_text(slots)

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

    # 6.5 Ambulatory adjustment: routine fever/cough/cold presentations without
    # red flags, severity, high temperature, or vulnerable age are video-consult
    # material — not a home visit.
    _AMBULATORY_SYMPTOMS = {"fever", "cough", "cold", "runny_nose", "headache", "weakness", "vomiting"}
    if (
        care_type in ("paramedic_home_visit", "home_nursing", "lab_test_home")
        and urgency_after_risk_modifiers in ("same_day", "scheduled")
        and slots.get("symptoms")
        and set(slots.get("symptoms", [])) <= _AMBULATORY_SYMPTOMS
        and slots.get("severity") in (None, "mild")
        and slots.get("age_group") not in ("child", "senior")
        and slots.get("patient_relation") in (None, "self", "")
        and not slots.get("pregnancy")
        and not slots.get("chronic_conditions")
        and not (request.patient and request.patient.age and request.patient.age >= 60)
        and slots.get("duration") not in ("More than a week", "एक हफ्ते से अधिक")
        and not (slots.get("fever_temp") is not None and float(slots.get("fever_temp") or 0) >= 103)
        and not high_flags
    ):
        care_type = "teleconsultation"
        urgency_after_risk_modifiers = "same_day"
        reasons.append("Stage 6.5 (Ambulatory adjustment): routine fever/cough/cold routed to teleconsultation")

    # 6.6 Injury sanity: routine pain/sprain/joint presentations are
    # video-consult material (an X-ray needs a hospital anyway) unless severe
    # or vulnerable. Misclassified home_nursing / lab routes for injuries are
    # corrected too.
    _prev_injury = care_type
    care_type, urgency_after_risk_modifiers = _apply_injury_sanity(
        care_type, urgency_after_risk_modifiers, slots, request.patient
    )
    if care_type != _prev_injury:
        reasons.append(f"Stage 6.6 (Injury sanity): {_prev_injury} -> {care_type}")

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
            confidence = 0.30
            reasons.append(f"Stage 7: Max follow-ups reached ({history_turns} turns); condition unclear. Defaulted to teleconsultation as safest first step.")
            reasons.append("not enough information")
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
                "screen_status": screen_status,
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
                context_key = "heat_wave"
                context_used = {
                    "season": season_display(context.get("season", "")),
                    "weather": f"{round(temp_c)}°C" if temp_c is not None else "Heat wave",
                    "aqi": aqi_val,
                    "location": context.get("location_name") or None,
                    "time": context.get("local_time_str") or None,
                    "tags": tags,
                    "reason": context_line(context_key, lang),
                }
                reasons.append("Context Escalation: Heat wave + senior + fever/restlessness escalated to emergency_112")

        if not is_emergency and ("poor_air" in tags or (aqi_val is not None and aqi_val >= 200)) and has_asthma:
            if any(s in slots.get("symptoms", []) for s in ["breathlessness", "cough", "saans"]):
                is_emergency = True
                context_key = "poor_air"
                context_used = {
                    "season": season_display(context.get("season", "")),
                    "weather": context.get("summary", ""),
                    "aqi": aqi_val,
                    "location": context.get("location_name") or None,
                    "time": context.get("local_time_str") or None,
                    "tags": tags,
                    "reason": context_line(context_key, lang),
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
            context_key = "night_rain"
            temp_val = round(context["temperature_c"]) if context.get("temperature_c") is not None else None
            precip = context.get("precipitation_mm") or 0
            is_rainy = "rainy" in context.get("tags", []) or precip >= 1.0
            if is_rainy:
                weather_desc = f"{temp_val}°C rainy" if temp_val is not None else "Rainy"
            else:
                weather_desc = f"{temp_val}°C night" if temp_val is not None else "Night-time"
            context_used = {
                "season": season_display(context.get("season", "")),
                "weather": weather_desc,
                "aqi": context.get("aqi"),
                "location": context.get("location_name") or None,
                "time": context.get("local_time_str") or None,
                "tags": context.get("tags", []),
                "reason": context_line(context_key, lang),
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

    # 8.5 LLM second opinion (ML-first). Runs AFTER the ML decision is final
    # (care_type is compared to care_type, flags to flags) and can only raise
    # severity: agree -> confidence up; more severe -> ask ONE confirmation
    # question (never decide); less severe -> ignored.
    second_opinion = None
    llm_opinion = run_second_opinion(user_input, lang)
    recon = reconcile_second_opinion(final_care_type, list(set(high_flags + ml_red_flags)), llm_opinion)
    if llm_opinion is not None:
        second_opinion = {
            "agrees": recon["agrees"],
            "llm_care_type": recon["llm_care_type"],
            "note": recon["note"],
            "reason": llm_opinion.get("reason", ""),
        }
        reasons.append(f"Stage 8.5 (Second opinion): {recon['note']}")

    if recon["agrees"]:
        confidence = round(min(confidence + 0.05, 0.99), 4)
    elif recon["ask"] and final_care_type != "emergency_112" and history_turns < settings.MAX_FOLLOWUPS:
        # LLM more severe than the final ML decision: ask ONE confirmation
        # question, never decide.
        ask_flags = recon.get("ask_flags") or []
        qid = flag_question_id(ask_flags[0]) if ask_flags else COMBINED_QUESTION_ID
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
            "screen_status": screen_status,
            "second_opinion": second_opinion,
            "ml_red_flags": ml_red_flags,
            "guardrails": {
                "input_guard": input_guard_res,
                "output_violations": output_violations,
                "template_replaced": template_replaced,
            },
            "reasons": reasons + ["Second opinion more severe than ML; asking one confirmation question"],
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
            context_used=None,
            second_opinion=second_opinion,
            debug=debug_trace if debug else None,
        )

    # 9. Explainability & Guardrail Enforcement: the card is short lines only.
    if unclear_fallback:
        unclear_why = {
            "en": "Could not be sure what you need.",
            "hinglish": "Samajh nahi aa paaya ki aapko kya chahiye.",
            "hi": "समझ नहीं आया कि आपको क्या चाहिए।",
        }.get(lang, "Could not be sure what you need.")
        card_lines = build_card_lines(
            care_type="teleconsultation", urgency="same_day", symptoms=[],
            duration=None, red_flags=[], language=lang,
            why_override=unclear_why,
        )
        reasoning = card_text(card_lines)
    else:
        card_lines = build_card_lines(
            care_type=final_care_type,
            urgency=final_urgency,
            symptoms=slots.get("symptoms", []),
            duration=slots.get("duration"),
            red_flags=high_flags,
            language=lang,
            context_key=context_key,
            chest_pain=slots.get("chest_pain"),
            breathing_difficulty=slots.get("breathing_difficulty"),
        )
        reasoning = card_text(card_lines)

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
        "extraction_source": slots.get("extraction_source"),
        "ml_red_flags": ml_red_flags,
        "second_opinion": second_opinion,
        "final_care_type": final_care_type,
        "final_urgency": final_urgency,
        "context_info": context,
        "screen_status": screen_status,
        "semantic_screen": {"status": screen_status, "flags": semantic_flags, "combined": combined_needed},
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
        secondary_options=secondary_doctor_options(final_care_type, lang),
        debug=debug_trace if debug else None,
        card_lines=card_lines,
        disclaimer=get_disclaimer(lang),
        second_opinion=second_opinion,
        details={
            "symptoms": slots.get("symptoms", []),
            "answers": {},
            "context_used": context_used,
            "confidence": round(confidence, 2) if confidence else None,
            "care_type": final_care_type,
            "urgency": final_urgency,
            "red_flags": high_flags,
            "ml_features": top_terms,
            "extraction_source": slots.get("extraction_source"),
        },
    )


def _screen_skip_precheck(request: TriageRequest) -> bool:
    """Mirrors the pipeline's own screen-skip conditions (bare answers,
    second follow-up answer, rules already emergency). Cheap & deterministic;
    used by the async wrapper to decide whether to parallelize."""
    user_input = (request.user_input or "").strip()
    if user_input.lower() in _BARE_ANSWERS:
        return True
    history_dicts = [{"role": m.role, "text": m.text or m.content or ""} for m in request.conversation_history]
    if count_assistant_turns(history_dicts) >= settings.MAX_FOLLOWUPS:
        return True
    try:
        _, _, _, is_high = check_red_flags(user_input, detect_and_normalise(user_input)[1], return_medium=True)
        return bool(is_high)
    except Exception:
        return False


async def run_triage_pipeline_async(
    request: TriageRequest,
    db: Session | None = None,
    debug: bool = False,
) -> TriageResponse:
    """Async /triage entry point. Runs the semantic screen and the intake
    extraction IN PARALLEL (asyncio.gather) to keep p95 latency under the
    budget; the screen runs on the fast model with its own 2.5 s timeout.
    Ineligible requests (emergencies, bare answers, second follow-up answers)
    take the synchronous path, where the screen is skipped anyway."""
    if _screen_skip_precheck(request):
        return run_triage_pipeline(request, db=db, debug=debug)

    user_input = (request.user_input or "").strip()
    input_guard_res = input_guard(user_input)
    cleaned_input = input_guard_res["cleaned_text"]
    try:
        _, norm_text, detected_lang = detect_and_normalise(cleaned_input)
    except Exception:
        return run_triage_pipeline(request, db=db, debug=debug)
    lang = request.language if request.language != "auto" else detected_lang

    history_dicts = [{"role": m.role, "text": m.text or m.content or ""} for m in request.conversation_history]

    loop = asyncio.get_running_loop()

    def _screen() -> dict:
        try:
            return screen_red_flags(user_input, lang)
        except Exception:
            return {"status": "skip", "flags": [], "combined": False}

    def _extract() -> dict | None:
        try:
            return extract_slots(norm_text, history_dicts)
        except Exception:
            return None

    screen_result, pre_slots = await asyncio.gather(
        loop.run_in_executor(None, _screen),
        loop.run_in_executor(None, _extract),
    )
    return run_triage_pipeline(
        request, db=db, debug=debug,
        screen_result=screen_result,
        pre_slots=pre_slots,
    )
