import re
import yaml
from pathlib import Path
from app.config import settings
from app.core.language import transliterate_devanagari_to_roman, normalise_text, is_phrase_negated

_RED_FLAGS: list[dict] = []


def _load_red_flags():
    global _RED_FLAGS
    if not _RED_FLAGS and settings.RED_FLAGS_FILE.exists():
        try:
            with open(settings.RED_FLAGS_FILE, "r", encoding="utf-8") as f:
                _RED_FLAGS = yaml.safe_load(f) or []
        except Exception as e:
            _RED_FLAGS = []


def check_red_flags(
    original_text: str,
    normalised_text: str = "",
    translated_en: str = "",
    return_medium: bool = False,
) -> tuple:
    """
    Checks for red flags across original text, transliterated/normalised text, and English text.
    Only HIGH-severity flags are returned in high_severity_flags (matches response red_flags contract).
    Returns:
        If return_medium is False (default): (high_severity_flags, highest_severity, has_immediate_emergency)
        If return_medium is True: (high_severity_flags, medium_severity_flags, highest_severity, has_immediate_emergency)
    """
    _load_red_flags()

    high_flags: list[str] = []
    medium_flags: list[str] = []
    has_high_severity = False
    highest_severity: str | None = None

    if not original_text and not normalised_text:
        if return_medium:
            return [], [], None, False
        return [], None, False

    # Create combined representations for maximum recall
    combined_roman = (
        (normalised_text or normalise_text(original_text))
        + " "
        + normalise_text(transliterate_devanagari_to_roman(original_text))
    )
    combined_raw = original_text + " " + (translated_en or "")

    for flag in _RED_FLAGS:
        flag_id = flag.get("id", "")
        severity = flag.get("severity", "medium")
        patterns_en = flag.get("patterns_en", [])
        patterns_hi = flag.get("patterns_hi", [])
        patterns_hinglish = flag.get("patterns_hinglish", [])
        requires_not_negated = flag.get("requires_not_negated", True)

        found = False

        # 1. Check Devanagari patterns against raw text
        for pat in patterns_hi:
            if pat in combined_raw:
                if requires_not_negated and is_phrase_negated(pat, combined_raw):
                    continue
                found = True
                break

        # 2. Check English patterns
        if not found:
            for pat in patterns_en:
                p_norm = normalise_text(pat)
                if re.search(rf"\b{re.escape(p_norm)}\b", combined_roman) or pat.lower() in combined_raw.lower():
                    if requires_not_negated and (
                        is_phrase_negated(pat, combined_raw) or is_phrase_negated(p_norm, combined_roman)
                    ):
                        continue
                    found = True
                    break

        # 3. Check Hinglish patterns
        if not found:
            for pat in patterns_hinglish:
                p_norm = normalise_text(pat)
                if p_norm in combined_roman or pat.lower() in combined_raw.lower():
                    if requires_not_negated and (
                        is_phrase_negated(pat, combined_raw) or is_phrase_negated(p_norm, combined_roman)
                    ):
                        continue
                    found = True
                    break

        if found:
            if severity == "high":
                if flag_id in settings.RED_FLAGS and flag_id not in high_flags:
                    high_flags.append(flag_id)
                has_high_severity = True
                highest_severity = "high"
            else:
                if flag_id not in medium_flags:
                    medium_flags.append(flag_id)
                if highest_severity != "high":
                    highest_severity = "medium"

    if return_medium:
        return high_flags, medium_flags, highest_severity, has_high_severity
    return high_flags, highest_severity, has_high_severity
