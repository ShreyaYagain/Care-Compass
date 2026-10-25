import re
import logging
import yaml
from pathlib import Path
from typing import Any
from app.config import settings

logger = logging.getLogger(__name__)

_LEXICON: dict = {}
_GUARDRAILS_CONFIG: dict = {}

LEXICON_FILE = Path(__file__).resolve().parent.parent / "data" / "guardrail_lexicon.yaml"
CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "guardrails.yaml"


def _load_guardrail_data():
    global _LEXICON, _GUARDRAILS_CONFIG
    if not _LEXICON and LEXICON_FILE.exists():
        try:
            with open(LEXICON_FILE, "r", encoding="utf-8") as f:
                _LEXICON = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load guardrail lexicon: {e}")
            _LEXICON = {}

    if not _GUARDRAILS_CONFIG and CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                _GUARDRAILS_CONFIG = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load guardrails config: {e}")
            _GUARDRAILS_CONFIG = {}


def get_disclaimer(lang: str = "en") -> str:
    _load_guardrail_data()
    disc = _GUARDRAILS_CONFIG.get("disclaimer", {})
    return disc.get(lang) or disc.get("en") or "This app helps you find the right care. It is not a doctor."


def get_escalation_line(lang: str = "en") -> str:
    _load_guardrail_data()
    esc = _GUARDRAILS_CONFIG.get("escalation_line", {})
    return esc.get(lang) or esc.get("en") or "If it gets worse or you notice breathing trouble, chest pain, confusion, or bleeding, call 112 or tell us right away."


def get_scope_refusal(lang: str = "en") -> str:
    _load_guardrail_data()
    ref = _GUARDRAILS_CONFIG.get("scope_refusal", {})
    return ref.get(lang) or ref.get("en") or "I can only assist with healthcare navigation. We can arrange a doctor home check, home nursing, a home lab test, or an online doctor consultation."


def get_deterministic_template(care_type: str, lang: str = "en") -> str:
    _load_guardrail_data()
    templates = _GUARDRAILS_CONFIG.get("deterministic_templates", {})
    type_templates = templates.get(care_type, {})
    text = type_templates.get(lang) or type_templates.get("en")
    if not text:
        fallbacks = {
            "paramedic_home_visit": "Medic home visit recommended for in-person assessment and vitals.",
            "home_nursing": "Home nursing visit recommended for required nursing care and procedures.",
            "lab_test_home": "Home diagnostic sample collection recommended for laboratory testing.",
            "teleconsultation": "Online doctor consultation recommended for clinical evaluation and guidance.",
            "emergency_112": "Critical symptoms detected. Routed to emergency services (112), not home care.",
        }
        text = fallbacks.get(care_type, "Timely healthcare assessment recommended.")
    return text


def input_guard(text: str) -> dict[str, Any]:
    """
    Sanitizes user input:
    - Masks phone numbers and email addresses.
    - Detects prompt injection in en/hi/hinglish.
    - Detects off-topic and abusive prompts.
    Returns:
      {
        "allowed": bool,
        "reason": str,
        "cleaned_text": str,
        "flags": list[str]
      }
    """
    try:
        _load_guardrail_data()
        flags = []
        cleaned = text

        # 1. PII Masking: Phone numbers & Emails
        # Indian phone numbers (+91, 10 digits) & standard phone patterns
        phone_pattern = r'(?:\+?91[\s-]?)?[6-9]\d{9}\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b'
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

        if re.search(phone_pattern, cleaned):
            cleaned = re.sub(phone_pattern, '[PHONE MASKED]', cleaned)
            flags.append("pii_phone_masked")

        if re.search(email_pattern, cleaned):
            cleaned = re.sub(email_pattern, '[EMAIL MASKED]', cleaned)
            flags.append("pii_email_masked")

        # 2. Prompt Injection detection
        injections = _LEXICON.get("prompt_injection_patterns", [])
        for pat in injections:
            if re.search(pat, text):
                flags.append("prompt_injection")
                return {
                    "allowed": False,
                    "reason": "Prompt injection pattern detected",
                    "cleaned_text": cleaned,
                    "flags": flags,
                }

        # 3. Abusive text detection
        abusive = _LEXICON.get("abusive_patterns", [])
        for pat in abusive:
            if re.search(pat, text):
                flags.append("abusive")
                return {
                    "allowed": False,
                    "reason": "Abusive language detected",
                    "cleaned_text": cleaned,
                    "flags": flags,
                }

        # 4. Off-topic detection
        off_topic = _LEXICON.get("off_topic_patterns", [])
        for pat in off_topic:
            if re.search(pat, text):
                flags.append("off_topic")
                return {
                    "allowed": False,
                    "reason": "Off-topic query detected",
                    "cleaned_text": cleaned,
                    "flags": flags,
                }

        return {
            "allowed": True,
            "reason": "Passed input guard",
            "cleaned_text": cleaned,
            "flags": flags,
        }

    except Exception as e:
        logger.error(f"Error in input_guard: {e}")
        return {
            "allowed": True,
            "reason": f"Input guard fallback on error: {e}",
            "cleaned_text": text,
            "flags": ["guard_error"],
        }


def output_guard(
    text: str,
    lang: str = "en",
    is_emergency: bool = False,
    care_type: str = "teleconsultation",
    field_name: str = "reasoning",
) -> dict[str, Any]:
    """
    Inspects user-facing text against clinical safety rules:
    - NEVER name a disease or condition.
    - NEVER mention drug names, doses, or home-remedy dosages.
    - NEVER give false reassurance.
    - NEVER discourage seeking care or calling 112.
    - Fail-safe: if violations are present or if evaluation fails, returns deterministic safe template.
    """
    try:
        if not text or not text.strip():
            return {"ok": True, "violations": [], "safe_text": text}

        _load_guardrail_data()
        violations = []
        lower_text = text.lower()

        # 1. Disease / diagnosis detection
        # Specific diagnostic phrases
        diag_patterns = [
            r'\b(?:you have|it is probably|looks like|diagnosed with|could be|suffering from)\s+([a-zA-Z]+)',
            r'\b(?:aapko|shayad|lagta hai ki)\s+([a-zA-Z\u0900-\u097F]+)\s+(?:hai|ho gaya)',
        ]
        for dp in diag_patterns:
            if re.search(dp, lower_text):
                violations.append("diagnostic_phrasing")

        diseases = _LEXICON.get("diseases", [])
        for dis in diseases:
            # Word boundary check for disease names
            pattern = rf'(?i)\b{re.escape(dis)}\b'
            if re.search(pattern, text):
                violations.append(f"disease_named:{dis}")
                break

        # 2. Medicine / Drug names & dosage patterns
        # The closed follow-up question bank may legitimately ask "are you
        # taking any medication?" (a factual question, never a recommendation),
        # so the drug-name scan is skipped for vetted bank questions.
        drugs = _LEXICON.get("drugs_and_medicines", [])
        if field_name != "follow_up_question":
            for drug in drugs:
                pattern = rf'(?i)\b{re.escape(drug)}\b'
                if re.search(pattern, text):
                    violations.append(f"drug_named:{drug}")
                    break

            dosage_pats = _LEXICON.get("dosage_patterns", [])
            for dpat in dosage_pats:
                if re.search(dpat, text):
                    violations.append("dosage_pattern_named")
                    break

        # 3. False reassurance
        reassurance = _LEXICON.get("false_reassurance_phrases", [])
        for r_phrase in reassurance:
            if r_phrase in lower_text:
                violations.append(f"false_reassurance:{r_phrase}")
                break

        # 4. Discouraging care
        discouraging = _LEXICON.get("discouraging_care_phrases", [])
        for d_phrase in discouraging:
            if d_phrase in lower_text:
                violations.append(f"discouraging_care:{d_phrase}")
                break

        if violations:
            logger.warning(f"Output guard violations found in {field_name}: {violations}")
            safe_text = get_deterministic_template(care_type, lang)
            # The card never carries the app disclaimer (it lives in the app's
            # Settings/About); only the safety line is attached.
            if field_name == "reasoning" and not is_emergency:
                safe_text = f"{safe_text} {get_escalation_line(lang)}"
            return {
                "ok": False,
                "violations": violations,
                "safe_text": safe_text,
            }

        return {
            "ok": True,
            "violations": [],
            "safe_text": text,
        }

    except Exception as e:
        logger.critical(f"Output guard exception: {e}; falling back to deterministic template.")
        safe_text = get_deterministic_template(care_type, lang)
        if field_name == "reasoning" and not is_emergency:
            safe_text = f"{safe_text} {get_escalation_line(lang)}"
        return {
            "ok": False,
            "violations": [f"guard_exception:{e}"],
            "safe_text": safe_text,
        }
