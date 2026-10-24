"""Deterministic pregnancy risk layer.

Runs BEFORE the LLM and the classifier. Pregnancy + a danger sign escalates
immediately (no follow-up question, never teleconsultation-only). Pregnancy
plus any complaint is at least same_day; pregnancy alone with a mild complaint
is at minimum same_day teleconsultation.

Official red flags are used wherever a danger sign maps to one; otherwise the
pipeline escalates via the pregnancy risk modifier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.language import normalise_text, is_phrase_negated

# ---------------------------------------------------------------------------
# Lexicon (English / Hinglish / Hindi)
# ---------------------------------------------------------------------------

PREGNANCY_TERMS_EN = [
    "pregnant",
    "pregnancy",
    "expecting",
    "expecting a baby",
    "with child",
]

PREGNANCY_TERMS_HINGLISH = [
    "garbhvati",
    "garbhavati",
    "garbhwati",
    "garbh se hai",
    "garbh hai",
    "garbh ka",
    "garbh ke",
    "garbh me",
    "garbh mein",
    "pet me bacha",
    "pet mein bacha",
    "pet me baccha",
    "pet mein baccha",
    "pet me bacha hai",
    "pet mein bacha hai",
    "bacha hone wali",
    "bachha hone wali",
    "bachhe wali",
    "bacche wali",
    "ma banne wali",
    "maa banne wali",
    "garbhdharan",
    "garbh dharan",
    "pregnant hai",
    "pregnant hu",
    "pregnancy hai",
    "pregnancy chal rahi",
    "expecting",
]

PREGNANCY_TERMS_HI = [
    "गर्भवती",
    "गर्भवती हैं",
    "गर्भ से है",
    "गर्भधारण",
    "गर्भ में बच्चा",
    "पेट में बच्चा",
    "पेट में बच्चा है",
    "माँ बनने वाली",
    "मां बनने वाली",
]

# Danger signs that map to official red flags when pregnancy is present.
BLEEDING_PATTERNS_EN = ["bleeding", "spotting", "bleeding heavily", "blood loss"]
BLEEDING_PATTERNS_HINGLISH = [
    "khoon aa raha",
    "khoon aa rahi",
    "khoon aa rahe",
    "khoon nikal raha",
    "khoon nikal rahi",
    "khoon beh raha",
    "khoon beh rahi",
    "khoon dikh raha",
    "khoon dikh rahi",
    "khoon lag raha",
    "khoon lag gaya",
    "spotting",
    "bleeding ho rahi",
    "bleeding ho raha",
]
BLEEDING_PATTERNS_HI = ["खून आ रहा", "खून आ रही", "खून निकल रहा", "रक्तस्राव", "खून बह रहा"]

FITS_PATTERNS_EN = ["fits", "convulsions", "convulsing", "seizure", "seizures"]
FITS_PATTERNS_HINGLISH = ["fits", "daura", "daure", "jhatke", "jhatka", "mirgi ka daura"]
FITS_PATTERNS_HI = ["दौरा", "दौरे", "झटके", "झटका", "मिर्गी"]

UNCONSCIOUS_PATTERNS_EN = ["unconscious", "fainted", "passed out", "blacked out"]
UNCONSCIOUS_PATTERNS_HINGLISH = ["behosh", "behoshi", "hosh kho", "hosh nahi", "beosh"]
UNCONSCIOUS_PATTERNS_HI = ["बेहोश", "बेहोशी", "होश नहीं"]

HEADACHE_PATTERNS = [
    "severe headache",
    "tez sar dard",
    "tez sir dard",
    "bahut tez sar dard",
    "sar me bahut dard",
    "sir me bahut dard",
    "headache",
    "sir dard",
    "sar dard",
]
VISION_SWELLING_PATTERNS = [
    "blurred vision",
    "blurry vision",
    "dhundhla",
    "dhudhla",
    "dhundla",
    "dhundhla dikh",
    "vision problem",
    "swelling",
    "sujan",
    "soojan",
    "chehre par sujan",
    "face sujan",
    "paon me sujan",
    "pair me sujan",
    "haath me sujan",
    "hath me sujan",
]

SEVERE_ABDOMINAL_PATTERNS = [
    "severe abdominal pain",
    "severe stomach pain",
    "severe stomach ache",
    "tez pet dard",
    "bahut tez pet dard",
    "pet me tez dard",
    "pet mein tez dard",
    "pet me bahut tez dard",
]

# Urgent-but-not-emergency signs (min same_day).
WATER_BROKE_PATTERNS = [
    "water broke",
    "water broken",
    "water bag burst",
    "paani toot gaya",
    "pani toot gaya",
    "paani toota",
    "pani toota",
    "jhol toot gaya",
]
BABY_NOT_MOVING_PATTERNS = [
    "baby not moving",
    "baby is not moving",
    "bacha hil nahi raha",
    "baccha hil nahi raha",
    "bacha movement nahi",
    "movement kam",
    "kick nahi aa rahi",
    "kick aa nahi rahi",
]
LABOUR_PAIN_PATTERNS = [
    "labour pain",
    "labour pains",
    "labour shuru",
    "labor pain",
    "contractions",
    "contraction",
]
HIGH_FEVER_PATTERNS = [
    "high fever",
    "tez bukhar",
    "bahut tez bukhar",
    "fever 101",
    "fever 102",
    "fever 103",
    "fever 104",
    "bukhar 101",
    "bukhar 102",
    "bukhar 103",
    "bukhar 104",
]


@dataclass
class PregnancyRisk:
    is_pregnant: bool = False
    emergency_flags: list[str] = field(default_factory=list)
    force_emergency: bool = False
    urgent_reasons: list[str] = field(default_factory=list)
    reason: str = ""


def _combined(text: str) -> str:
    return normalise_text(text)


def _match_any(patterns: list[str], text: str) -> bool:
    for pat in patterns:
        p_norm = normalise_text(pat)
        if re.search(rf"\b{re.escape(p_norm)}\b", text):
            if is_phrase_negated(pat, text) or is_phrase_negated(p_norm, text):
                continue
            return True
    return False


def detect_pregnancy(text: str) -> bool:
    """True when the text states a pregnancy (self, wife, bahu, behen, etc.)."""
    combined = _combined(text)
    if not combined:
        return False
    for pat in PREGNANCY_TERMS_EN + PREGNANCY_TERMS_HINGLISH:
        p_norm = normalise_text(pat)
        if re.search(rf"\b{re.escape(p_norm)}\b", combined):
            if is_phrase_negated(p_norm, combined):
                continue
            return True
    for pat in PREGNANCY_TERMS_HI:
        p_norm = normalise_text(pat)
        if re.search(rf"\b{re.escape(p_norm)}\b", combined):
            if is_phrase_negated(p_norm, combined):
                continue
            return True
    # "X weeks/months pregnant" / "X hafte/mahine ki garbhvati"
    if re.search(r"\b\d{1,2}\s+(weeks?|months?|hafte|mahine)\s+(pregnant|garbhvati|garbhavati|garbh)\b", combined):
        return True
    return False


def check_pregnancy(text: str) -> PregnancyRisk:
    """Deterministic pregnancy risk check. Never crashes."""
    result = PregnancyRisk()
    if not text:
        return result
    combined = _combined(text)
    result.is_pregnant = detect_pregnancy(text)
    if not result.is_pregnant:
        return result

    reasons: list[str] = []

    # 1. Vaginal bleeding -> severe_bleeding (emergency_112)
    if _match_any(BLEEDING_PATTERNS_EN, combined) or \
            _match_any(BLEEDING_PATTERNS_HINGLISH, combined) or \
            _match_any(BLEEDING_PATTERNS_HI, combined):
        result.emergency_flags.append("severe_bleeding")
        reasons.append("pregnancy with vaginal bleeding")

    # 2. Fits / convulsions / behoshi -> seizure / unconsciousness (emergency_112)
    if _match_any(FITS_PATTERNS_EN, combined) or \
            _match_any(FITS_PATTERNS_HINGLISH, combined) or \
            _match_any(FITS_PATTERNS_HI, combined):
        if "seizure" not in result.emergency_flags:
            result.emergency_flags.append("seizure")
        reasons.append("pregnancy with fits/convulsions")
    if _match_any(UNCONSCIOUS_PATTERNS_EN, combined) or \
            _match_any(UNCONSCIOUS_PATTERNS_HINGLISH, combined) or \
            _match_any(UNCONSCIOUS_PATTERNS_HI, combined):
        if "unconsciousness" not in result.emergency_flags:
            result.emergency_flags.append("unconsciousness")
        reasons.append("pregnancy with unconsciousness")

    # 3. Severe headache + blurred vision/swelling -> stroke_symptoms
    has_headache = any(re.search(rf"\b{re.escape(normalise_text(p))}\b", combined) for p in HEADACHE_PATTERNS)
    has_vision_swelling = any(re.search(rf"\b{re.escape(normalise_text(p))}\b", combined) for p in VISION_SWELLING_PATTERNS)
    if has_headache and has_vision_swelling:
        if "stroke_symptoms" not in result.emergency_flags:
            result.emergency_flags.append("stroke_symptoms")
        reasons.append("pregnancy with severe headache and blurred vision/swelling")

    # 4. Severe abdominal pain -> emergency via risk modifier (no official flag)
    if _match_any(SEVERE_ABDOMINAL_PATTERNS, combined):
        result.force_emergency = True
        reasons.append("pregnancy with severe abdominal pain")

    # 5. Urgent signs -> at least same_day
    if _match_any(WATER_BROKE_PATTERNS, combined):
        result.urgent_reasons.append("water broke")
    if _match_any(BABY_NOT_MOVING_PATTERNS, combined):
        result.urgent_reasons.append("baby not moving")
    if _match_any(LABOUR_PAIN_PATTERNS, combined):
        result.urgent_reasons.append("labour pains")
    if _match_any(HIGH_FEVER_PATTERNS, combined):
        result.urgent_reasons.append("fever in pregnancy")

    result.reason = "; ".join(reasons + result.urgent_reasons)
    return result
