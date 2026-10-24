"""Follow-up MODULES: closed, symptom-selected multi-field question cards.

A module is chosen by the extracted symptom (injury/fall, fever, abdominal
pain, cough/breathing, ...). The card is a single turn with buttons/sliders in
the user's language. Anything already stated in the message is prefilled and
the corresponding field is hidden. The LLM may only select the module id and
which fields are still unanswered; it never writes free-form questions.
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
    back to the deterministic symptom-based selection."""
    deterministic = detect_module(slots)
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
) -> Optional[dict]:
    """Builds the card definition: only the still-unanswered fields, localised.

    Returns None when the module id is unknown or every field is already
    answered (then the caller decides directly).
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
# Injury / fall deterministic decision rules
# ---------------------------------------------------------------------------

_WEIGHT_NOT_AT_ALL = {"Not at all", "Bilkul nahi"}


def injury_decision(answers: dict, slots: dict) -> dict:
    """Deterministic decision for the injury module. Never diagnoses.

    Returns {"care_type", "urgency", "red_flags", "reason"}.
    """
    pain = _as_int(answers.get("pain_level"))
    swelling = answers.get("swelling") == "Yes"
    weight = answers.get("weight_bearing", "")
    deformity = answers.get("deformity") == "Yes"
    neuro = answers.get("neuro_vascular") == "Yes"
    head_hit = answers.get("head_hit") == "Yes"
    fall_type = answers.get("fall_type", "")

    is_elderly = (
        slots.get("age_group") == "senior"
        or slots.get("patient_relation") in {"grandmother", "grandfather", "senior", "dada", "dadi", "mother", "father"}
    )

    hospital_line = ("If it worsens, go to hospital or call 112. This could need an X-ray; a doctor should check it.")

    # 1. Head hit + drowsy/faint -> unconsciousness -> emergency_112
    if head_hit:
        return {
            "care_type": "emergency_112",
            "urgency": "emergency",
            "red_flags": ["unconsciousness"],
            "reason": "Head injury after a fall can be serious; emergency services (112) are recommended immediately.",
        }

    # 2. High-risk limb injury -> paramedic_home_visit (same_day) + hospital line
    high_risk_limb = (
        (pain >= 8 and (deformity or weight in _WEIGHT_NOT_AT_ALL))
        or neuro
        or fall_type in ("From height", "Road accident")
    )
    if high_risk_limb:
        return {
            "care_type": "paramedic_home_visit",
            "urgency": "same_day",
            "red_flags": [],
            "reason": (
                f"Pain {pain}/10" + (", swelling" if swelling else "") +
                (", cannot bear weight" if weight in _WEIGHT_NOT_AT_ALL else "") +
                (", numbness/cold limb" if neuro else "") +
                f", so a medic home visit is recommended. {hospital_line}"
            ),
        }

    # 3. Elderly hip/thigh after fall -> same_day minimum
    if is_elderly and pain >= 4:
        return {
            "care_type": "paramedic_home_visit",
            "urgency": "same_day",
            "red_flags": [],
            "reason": f"Elderly patient with hip/thigh pain after a fall: a same-day medic home visit is recommended. {hospital_line}",
        }

    # 4. Moderate pain + swelling, some weight bearing -> paramedic or teleconsultation
    if 4 <= pain <= 7 and swelling:
        return {
            "care_type": "paramedic_home_visit",
            "urgency": "same_day",
            "red_flags": [],
            "reason": f"Pain {pain}/10 with swelling and some weight bearing, so a medic home visit is recommended; this could need an X-ray. {hospital_line}",
        }

    # 5. Mild pain, no swelling, normal movement -> teleconsultation
    return {
        "care_type": "teleconsultation",
        "urgency": "same_day",
        "red_flags": [],
        "reason": f"Pain {pain}/10 with normal movement, so a virtual doctor consultation is recommended to check whether an X-ray is needed.",
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
    if "pain_level" in answers and "severity" not in slots:
        try:
            p = int(answers["pain_level"])
            slots["severity"] = "severe" if p >= 7 else ("moderate" if p >= 4 else "mild")
        except Exception:
            pass
    if answers.get("duration") and not slots.get("duration"):
        slots["duration"] = answers["duration"]
    if answers.get("age_group") and not slots.get("age_group"):
        slots["age_group"] = str(answers["age_group"]).lower()
    if answers.get("swelling") == "Yes":
        slots["swelling"] = True
    if answers.get("vomiting") == "Yes":
        if "vomiting" not in slots.get("symptoms", []):
            slots.setdefault("symptoms", []).append("vomiting")
    if answers.get("breathing_difficulty") == "Yes":
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
