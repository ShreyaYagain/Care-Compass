import re
import yaml
from pathlib import Path
from app.config import settings
from app.core.language import transliterate_devanagari_to_roman, normalise_text, is_phrase_negated

_RED_FLAGS: list[dict] = []

# ---------------------------------------------------------------------------
# Fuzzy breathlessness matching (typos like breath/breathe/brethe, "cant",
# third-person subjects like dad/papa/maa/etc. are matched text-wide).
# ---------------------------------------------------------------------------

_BREATH_FUZZY_PATTERNS = [
    r"(?:stopped|stop|stopped)\s+(?:breath|breathe|brethe|brething|breathing)\b",
    r"(?:not|isn t|isnt|no longer)\s+(?:breath|breathe|brethe|brething|breathing)\b",
    r"(?:cant|can t|cannot)\s+(?:breath|breathe|brethe|breth|breathing|brething|breating|breathin)\b",
    r"(?:not able to|unable to|struggling to)\s+(?:breath|breathe|brethe|breth|breathing|brething|breating|breathin)\b",
    r"\b(?:saans|sans)\s+(?:nahi aa|nahi le pa|atak|ruk)\s+\w+",
    r"\b(?:dum|dam)\s+ghut\s+\w+",
]

# Milder breathing complaints route to a same-day doctor/medic visit, not 112.
_DIFFICULTY_FUZZY_PATTERNS = [
    r"(?:difficulty|difficult|hard|trouble)\s+(?:in\s+|to\s+)?(?:breath|breathe|brethe|brething|breathing)\b",
    r"\b(?:breathing|brething|breating)\s+(?:problem|difficulty|trouble)\b",
    r"\b(?:saans|sans)\s+(?:lene\s+)?(?:me|mein)\s+(?:dikkat|takleef|problem|pareshani)\b",
    r"\b(?:saans|sans)\s+(?:phool|phul)\s+\w+",
]


def _matches_fuzzy(patterns: list[str], text: str) -> bool:
    for pat in patterns:
        for m in re.finditer(pat, text):
            phrase = m.group(0)
            if is_phrase_negated(phrase, text):
                continue
            return True
    return False


def _fuzzy_breathless(text: str) -> bool:
    """Typo-tolerant stopped/severe breathing detection used as an extra
    matching surface for the official breathlessness red flag."""
    return _matches_fuzzy(_BREATH_FUZZY_PATTERNS, text)


def _fuzzy_breathing_difficulty(text: str) -> bool:
    """Typo-tolerant detection of milder breathing difficulty."""
    return _matches_fuzzy(_DIFFICULTY_FUZZY_PATTERNS, text)


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
    evidence: dict | None = None,
) -> tuple:
    """
    Checks for red flags across original text, transliterated/normalised text, and English text.
    Only HIGH-severity flags are returned in high_severity_flags (matches response red_flags contract).
    If `evidence` is a dict, it is populated with {flag_id: matched_pattern_text} for each
    flag that matched (used for the debug `red_flag_sources` field).
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

    # Create combined representations for maximum recall.
    # " zzsepzzz " marks the boundary between the two representations so the
    # negation window in is_phrase_negated never spans the duplicate text.
    combined_roman = (
        (normalised_text or normalise_text(original_text))
        + " zzsepzzz "
        + normalise_text(transliterate_devanagari_to_roman(original_text))
    )
    combined_raw = original_text + " . " + (translated_en or "")

    for flag in _RED_FLAGS:
        flag_id = flag.get("id", "")
        severity = flag.get("severity", "medium")
        patterns_en = flag.get("patterns_en", [])
        patterns_hi = flag.get("patterns_hi", [])
        patterns_hinglish = flag.get("patterns_hinglish", [])
        requires_not_negated = flag.get("requires_not_negated", True)

        found = False
        matched_pat = ""

        # 1. Check Devanagari patterns (transliterated to Roman, word-boundary match)
        for pat in patterns_hi:
            p_norm = normalise_text(pat)
            if re.search(rf"\b{re.escape(p_norm)}\b", combined_roman):
                if requires_not_negated and (
                    is_phrase_negated(pat, combined_raw) or is_phrase_negated(p_norm, combined_roman)
                ):
                    continue
                found = True
                matched_pat = pat
                break

        # 2. Check English patterns (word-boundary match on normalised text)
        if not found:
            for pat in patterns_en:
                p_norm = normalise_text(pat)
                if re.search(rf"\b{re.escape(p_norm)}\b", combined_roman):
                    if requires_not_negated and (
                        is_phrase_negated(pat, combined_raw) or is_phrase_negated(p_norm, combined_roman)
                    ):
                        continue
                    found = True
                    matched_pat = pat
                    break

        # 3. Check Hinglish patterns (word-boundary match on normalised text)
        if not found:
            for pat in patterns_hinglish:
                p_norm = normalise_text(pat)
                if re.search(rf"\b{re.escape(p_norm)}\b", combined_roman):
                    if requires_not_negated and (
                        is_phrase_negated(pat, combined_raw) or is_phrase_negated(p_norm, combined_roman)
                    ):
                        continue
                    found = True
                    matched_pat = pat
                    break

        # 4. Fuzzy surfaces (typo-tolerant, negation-aware)
        if not found and flag_id == "breathlessness":
            if _fuzzy_breathless(combined_roman):
                found = True
                matched_pat = "(fuzzy breathless)"
        if not found and flag_id == "breathing_difficulty":
            if _fuzzy_breathing_difficulty(combined_roman):
                found = True
                matched_pat = "(fuzzy breathing difficulty)"

        if found:
            if evidence is not None and flag_id not in evidence:
                evidence[flag_id] = matched_pat
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
