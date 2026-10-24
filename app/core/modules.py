"""Follow-up MODULES: closed, symptom-selected single-question follow-ups.

A module is chosen by the extracted symptom (injury/fall, fever, abdominal
pain, cough/breathing, ...). Follow-ups are asked ONE question per turn
(buttons/slider, in the user's language), at most MODULE_MAX_QUESTIONS, and
the flow stops as soon as the case is determined. Anything already stated in
the message is prefilled and the corresponding question is skipped. The LLM
may only select the module id and which fields are still unanswered; it never
writes free-form questions.
"""
from __future__ import annotations

import re
from typing import Optional

import yaml

from app.config import settings
from app.core.language import normalise_text

_MODULES: dict = {}


def load_modules() -> dict:
    global _MODULES
    if not _MODULES:
        try:
            with open(settings.MODULES_FILE, "r", encoding="utf-8") as f:
                _MODULES = yaml.safe_load(f) or {}
        except Exception:
            _MODULES = {}
    return _MODULES


def module_ids() -> list[str]:
    return list((load_modules().get("modules") or {}).keys())


def _lang(lang: str | None) -> str:
    return lang if lang in ("en", "hi", "hinglish") else "en"


def _field_label(field: dict, key: str, lang: str) -> str:
    return field.get(f"{key}_{lang}") or field.get(f"{key}_en") or ""


def _option_labels(field: dict, lang: str) -> list[str]:
    out = []
    for o in field.get("options", []) or []:
        if isinstance(o, dict):
            out.append(o.get(lang) or o.get("en") or "")
        else:
            out.append(str(o))
    return out


def _answer_evidence_in_text(field: dict, text: str) -> bool:
    """True when the message already states this field's answer."""
    for k in field.get("evidence", []) or []:
        if re.search(rf"\b{re.escape(normalise_text(k))}\b", normalise_text(text)):
            return True
    return False


def detect_module(slots: dict) -> Optional[str]:
    """Deterministic module selection from the extracted symptoms."""
    symptoms = set(slots.get("symptoms", []))
    modules = (load_modules().get("modules") or {})
    for mid, m in modules.items():
        if any(s in symptoms for s in (m.get("trigger_symptoms") or [])):
            return mid
    return None


def llm_select_module(text: str, slots: dict) -> Optional[str]:
    """LLM override for module selection (structured, no free-form text). Falls
    back to the deterministic symptom-based selection.

    Never selects a module when no symptom was recognised, so the LLM cannot
    hallucinate a module for gibberish/irrelevant input."""
    if not slots.get("symptoms"):
        return None
    deterministic = detect_module(slots)
    symptoms = set(slots.get("symptoms", []) or [])
    modules = (load_modules().get("modules") or {})
    try:
        from app.core.llm import llm_json, is_llm_available
        from pydantic import BaseModel

        class ModuleSelection(BaseModel):
            module_id: str = ""
            answered_field_ids: list[str] = []

        if is_llm_available():
            sys = (
                "You select which closed follow-up MODULE matches a patient message and "
                "which of its fields are ALREADY answered in the message. You must NOT write "
                "any question text. Valid module ids: " + ", ".join(module_ids()) + ".\n"
                "Return JSON: {\"module_id\": str, \"answered_field_ids\": [str]}."
            )
            out = llm_json(system=sys, user=f"Message: \"{text}\"", schema=ModuleSelection)
            if out and out.module_id in module_ids():
                # Guardrail: a module is only acceptable when its trigger
                # symptoms are actually present in the extracted symptoms
                # (a plain headache must never open the injury module).
                m = modules.get(out.module_id) or {}
                triggers = set(m.get("trigger_symptoms") or [])
                if triggers & symptoms or out.module_id == deterministic:
                    return out.module_id
    except Exception:
        pass
    return deterministic


def _is_filled(slots: dict, field: dict, answered: set[str]) -> bool:
    fid = field.get("id")
    if fid in answered:
        return True
    slot = field.get("slot")
    if slot == "severity":
        return slots.get("severity") is not None
    if slot == "duration":
        return slots.get("duration") is not None
    if slot == "age_group":
        return slots.get("age_group") is not None or slots.get("patient_relation") not in (None, "self", "")
    if slot == "breathing_difficulty":
        return slots.get("breathing_difficulty") is not None
    if slot == "swelling":
        return slots.get("swelling") is not None
    if slot == "pregnancy":
        return slots.get("pregnancy") is not None
    return False


def render_module_card(
    module_id: str,
    lang: str,
    slots: dict,
    text: str = "",
    answered: list[str] | None = None,
    only_field: Optional[str] = None,
) -> Optional[dict]:
    """Builds a card definition: only the still-unanswered fields, localised.

    Follow-ups are asked ONE at a time: pass `only_field` to render the single
    next question. Returns None when the module id is unknown or the requested
    field is already answered (prefilled from slots or stated in the message).
    """
    modules = (load_modules().get("modules") or {})
    m = modules.get(module_id)
    if not m:
        return None

    lang = _lang(lang)
    answered_set = set(answered or [])
    norm = normalise_text(text or "")

    fields_out = []
    for field in m.get("fields", []) or []:
        fid = field.get("id")
        if only_field and fid != only_field:
            continue
        already = _is_filled(slots, field, answered_set) or _answer_evidence_in_text(field, norm)
        if already:
            continue
        ftype = field.get("type", "choice")
        entry = {
            "id": fid,
            "type": ftype,
            "question": _field_label(field, "question", lang),
            "informational": bool(field.get("informational", False)),
        }
        if ftype == "slider010":
            bands = field.get("bands", {})
            entry["bands"] = {
                "low": (bands.get(lang) or bands.get("en") or {}).get("low", "Mild"),
                "mid": (bands.get(lang) or bands.get("en") or {}).get("mid", "Moderate"),
                "high": (bands.get(lang) or bands.get("en") or {}).get("high", "Severe"),
            }
        else:
            entry["options"] = _option_labels(field, lang)
        fields_out.append(entry)

    if not fields_out:
        return None

    return {
        "module_id": module_id,
        "label": _field_label(m, "label", lang),
        "fields": fields_out,
    }


# ---------------------------------------------------------------------------
# Sequential follow-up flow: ONE question per turn, at most MODULE_MAX_QUESTIONS.
# ---------------------------------------------------------------------------

MODULE_MAX_QUESTIONS = 4


def _is_elderly(slots: dict) -> bool:
    return (
        slots.get("age_group") == "senior"
        or slots.get("patient_relation") in {"grandmother", "grandfather", "senior", "dada", "dadi", "mother", "father"}
    )


def injury_next_question(answers: dict, slots: dict) -> Optional[str]:
    """The single next question for the injury module, or None when the case
    is already determined (decide immediately)."""
    if not answers.get("head_hit"):
        return "head_hit"
    if _yes(answers.get("head_hit")):
        return None  # emergency_112, no more questions
    if answers.get("pain_level") is None:
        return "pain_level"
    pain = _as_int(answers.get("pain_level"))
    if pain < 4 or pain >= 8:
        return None  # mild -> teleconsultation; severe -> medic/112
    if _is_elderly(slots):
        return None  # elderly hip/thigh after fall -> same_day minimum
    if not answers.get("weight_bearing"):
        return "weight_bearing"
    if str(answers.get("weight_bearing")) in _WEIGHT_NOT_AT_ALL:
        return None  # cannot bear weight -> medic home visit
    if not answers.get("swelling"):
        return "swelling"
    return None  # answered everything that matters -> decide


def module_next_question(module_id: str, answers: dict, slots: dict) -> Optional[str]:
    """Next unanswered question for any module (injury has its own adaptive
    order; the other modules are asked in field order)."""
    if module_id == "injury":
        return injury_next_question(answers, slots)
    modules = (load_modules().get("modules") or {})
    m = modules.get(module_id)
    if not m:
        return None
    for field in m.get("fields", []) or []:
        if field.get("id") not in answers:
            return field.get("id")
    return None


# ---------------------------------------------------------------------------
# Injury / fall deterministic decision rules
# ---------------------------------------------------------------------------

_WEIGHT_NOT_AT_ALL = {"Not at all", "Bilkul nahi", "बिल्कुल नहीं"}
_FALL_HIGH = {"From height", "Road accident", "ऊँचाई से", "सड़क दुर्घटना"}
_YES = {"Yes", "हाँ", "Haan", "haan"}


def _yes(v) -> bool:
    return str(v or "") in _YES


def injury_decision(answers: dict, slots: dict, classifier_fn=None) -> dict:
    """Deterministic decision for the injury module. Never diagnoses.

    `classifier_fn(answers, slots)` optionally returns a
    (care_type, urgency, probs, confidence) tuple; its calibrated
    P(emergency_112) is the ONLY thing that may escalate a high-risk limb
    injury from paramedic_home_visit to emergency_112 (per policy:
    P >= 0.75). Pain alone is never escalated. Field 7 (meds_used) is never
    part of the decision.

    Returns {"care_type", "urgency", "red_flags", "reason"}.
    """
    pain = _as_int(answers.get("pain_level"))
    swelling = _yes(answers.get("swelling"))
    weight = str(answers.get("weight_bearing", "") or "")
    deformity = _yes(answers.get("deformity"))
    neuro = _yes(answers.get("neuro_vascular"))
    head_hit = _yes(answers.get("head_hit"))
    fall_type = str(answers.get("fall_type", "") or "")
    bleeding = slots.get("bleeding") is True or _yes(answers.get("bleeding"))

    hospital_line = ("If it worsens, go to hospital or call 112. This could need an X-ray; a doctor should check it.")
    summary = f"Pain {pain}/10" if pain >= 0 else ""
    if swelling:
        summary += ", swelling"
    if weight in _WEIGHT_NOT_AT_ALL:
        summary += ", cannot bear weight"
    if weight == "With pain":
        summary += ", weight bearing with pain"
    if neuro:
        summary += ", numb/cold limb"
    if fall_type:
        summary += f", fall: {fall_type}"

    # 1. Head hit + drowsy/faint -> unconsciousness -> emergency_112
    if head_hit:
        return {
            "care_type": "emergency_112",
            "urgency": "emergency",
            "red_flags": ["unconsciousness"],
            "reason": "Head injury after a fall can be serious; emergency services (112) are recommended immediately.",
        }

    # 2. Heavy bleeding / bone visible with bleeding -> severe_bleeding -> emergency_112
    if bleeding:
        return {
            "care_type": "emergency_112",
            "urgency": "emergency",
            "red_flags": ["severe_bleeding"],
            "reason": "Heavy bleeding after an injury needs immediate emergency care; call 112 now.",
        }

    fall_high = fall_type in _FALL_HIGH

    # 3. High-risk limb injury -> paramedic_home_visit (same_day) + hospital
    # line. Pain alone (even 8-10) is NEVER escalated to emergency_112; only a
    # serious combined finding (deformity, cannot bear weight, numb/cold limb,
    # fall from height) may escalate, and only when the calibrated classifier
    # is highly confident (P(emergency_112) >= 0.75).
    high_risk_limb = (
        fall_high
        or neuro
        or (pain >= 4 and (deformity or weight in _WEIGHT_NOT_AT_ALL))
    )
    if high_risk_limb and classifier_fn is not None:
        try:
            out = classifier_fn(answers, slots)
            if out and len(out) >= 3:
                probs = out[2] or {}
                p_emerg = float(probs.get("emergency_112", 0.0) or 0.0)
                if p_emerg >= 0.75:
                    return {
                        "care_type": "emergency_112",
                        "urgency": "emergency",
                        "red_flags": [],
                        "reason": (
                            f"{summary} and the triage model flags high risk, so emergency "
                            f"services (112) are recommended. {hospital_line}"
                        ),
                    }
        except Exception:
            pass
    if pain >= 8 or high_risk_limb:
        return {
            "care_type": "paramedic_home_visit",
            "urgency": "same_day",
            "red_flags": [],
            "reason": f"{summary}, so a medic home visit is recommended. {hospital_line}",
        }

    # 4. Elderly hip/thigh after fall -> same_day minimum
    if _is_elderly(slots) and pain >= 4:
        return {
            "care_type": "paramedic_home_visit",
            "urgency": "same_day",
            "red_flags": [],
            "reason": f"Elderly patient with hip/thigh pain after a fall: a same-day medic home visit is recommended. {hospital_line}",
        }

    # 5. Moderate pain + swelling with SOME weight bearing: the leg is usable,
    # so a doctor video consult is the realistic first step (an X-ray may be
    # needed; go to hospital if it worsens). Cannot-bear-weight already routed
    # above to a medic home visit.
    if 4 <= pain <= 7 and swelling:
        return {
            "care_type": "teleconsultation",
            "urgency": "same_day",
            "red_flags": [],
            "reason": f"{summary} and you can still bear some weight, so a doctor video consult is recommended; this may need an X-ray, which a hospital can do. If it worsens, go to hospital or call 112.",
        }

    # 6. Insufficient information (should not normally happen; the questions
    # always run first) -> safest first step.
    if pain < 0:
        return {
            "care_type": "teleconsultation",
            "urgency": "same_day",
            "red_flags": [],
            "reason": "We could not be sure about the injury, so a virtual doctor consultation is the safest first step to check whether an X-ray is needed.",
        }

    # 7. Mild pain, no swelling, normal movement -> teleconsultation
    return {
        "care_type": "teleconsultation",
        "urgency": "same_day",
        "red_flags": [],
        "reason": f"{summary}; normal movement, so a virtual doctor consultation is recommended to check whether an X-ray is needed.",
    }


def _as_int(v) -> int:
    try:
        return int(v)
    except Exception:
        return -1


def merge_answers_into_slots(slots: dict, answers: dict) -> None:
    """Merges module answers into the intake slots for non-injury modules."""
    if not answers:
        return
    if "pain_level" in answers and not slots.get("severity"):
        try:
            p = int(answers["pain_level"])
            slots["severity"] = "severe" if p >= 7 else ("moderate" if p >= 4 else "mild")
        except Exception:
            pass
    if answers.get("duration") and not slots.get("duration"):
        d = str(answers["duration"]).strip().lower()
        if d in ("today", "aaj se", "आज से"):
            slots["duration"] = "today"
        elif d in ("2-3 days", "2-3 din se", "2-3 दिन"):
            slots["duration"] = "2-3 days"
        elif d in ("more than a week", "ek hafte se zyada", "एक हफ्ते से अधिक"):
            slots["duration"] = "More than a week"
        elif d in ("hours", "ghante", "घंटे"):
            slots["duration"] = "today"
        elif d in ("days", "din", "दिन"):
            slots["duration"] = "2-3 days"
        elif d in ("weeks", "hafte", "हफ्ते"):
            slots["duration"] = "More than a week"
        else:
            slots["duration"] = answers["duration"]
    if answers.get("age_group") and not slots.get("age_group"):
        slots["age_group"] = str(answers["age_group"]).lower()
    if answers.get("temperature") and slots.get("fever_temp") is None:
        t = str(answers["temperature"]).lower()
        if "below" in t:
            slots["fever_temp"] = 99
        elif "above" in t:
            slots["fever_temp"] = 103
        else:
            slots["fever_temp"] = 101
        slots["fever_temp_unit"] = "F"
    if _yes(answers.get("rash")) and "rash" not in slots.get("symptoms", []):
        slots.setdefault("symptoms", []).append("rash")
    if _yes(answers.get("swelling")):
        slots["swelling"] = True
    if _yes(answers.get("vomiting")):
        if "vomiting" not in slots.get("symptoms", []):
            slots.setdefault("symptoms", []).append("vomiting")
    if _yes(answers.get("breathing_difficulty")):
        slots["breathing_difficulty"] = True
    if answers.get("meds_used"):
        slots["meds_used"] = answers["meds_used"]


def summarize_answers(answers: dict) -> str:
    """Human-readable summary of the module answers (used in the explanation)."""
    parts = []
    if answers.get("pain_level") is not None:
        parts.append(f"pain {answers['pain_level']}/10")
    for key, label in [
        ("swelling", "swelling"), ("weight_bearing", "weight bearing"),
        ("deformity", "deformity"), ("neuro_vascular", "numb/cold limb"),
        ("head_hit", "head hit"), ("fall_type", "fall type"),
        ("meds_used", "meds used"),
    ]:
        v = answers.get(key)
        if v:
            parts.append(f"{label}: {v}")
    return ", ".join(parts)
