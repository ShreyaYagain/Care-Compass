import json
import re
import string
from pathlib import Path
from app.config import settings

# Load Hinglish normalisation dictionary
_HINGLISH_NORM: dict[str, str] = {}
if settings.HINGLISH_NORM_FILE.exists():
    try:
        with open(settings.HINGLISH_NORM_FILE, "r", encoding="utf-8") as f:
            _HINGLISH_NORM = json.load(f)
    except Exception:
        _HINGLISH_NORM = {}

# Marker words for Hinglish
HINGLISH_MARKERS = {
    "hai", "ho", "raha", "rahi", "rahe", "ko", "se", "aur", "nahi", "nahin",
    "bhi", "mein", "me", "ka", "ki", "ke", "kya", "toh", "bohot", "bahut",
    "bukhar", "dard", "saans", "khansi", "dawa", "dawai", "tabiyat", "pet",
    "sir", "sar", "chhati", "seene", "doctor", "papa", "mummy", "dadi", "bache"
}

NEGATION_WORDS = {
    "no", "not", "none", "without", "never",
    "nahi", "nahin", "nahim", "na", "bina", "mat", "nhi"
}


def detect_script_and_language(text: str) -> str:
    """
    Detect language: 'hi' for Devanagari, 'hinglish' if latin contains Hindi markers, else 'en'.
    """
    if not text or not text.strip():
        return "en"

    # Count Devanagari Unicode characters (0900-097F)
    devanagari_count = sum(1 for c in text if "\u0900" <= c <= "\u097f")
    total_alpha = sum(1 for c in text if c.isalpha())

    if total_alpha > 0 and (devanagari_count / total_alpha) > 0.35:
        return "hi"

    # Check words for Hinglish
    tokens = [w.lower().strip(string.punctuation) for w in text.split()]
    hinglish_match = sum(1 for w in tokens if w in HINGLISH_MARKERS)

    if hinglish_match >= 1 or any(w in HINGLISH_MARKERS for w in tokens):
        return "hinglish"

    return "en"


def transliterate_devanagari_to_roman(text: str) -> str:
    """
    Transliterate Devanagari to Roman (ITRANS / Harvard-Kyoto or simple mapping).
    """
    devanagari_count = sum(1 for c in text if "\u0900" <= c <= "\u097f")
    if devanagari_count == 0:
        return text

    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import SchemeMap, SCHEMES, transliterate
        roman_text = transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS)
        return roman_text.lower()
    except Exception:
        # Fallback basic Devanagari to Roman transliteration
        charmap = {
            "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
            "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "क": "k", "ख": "kh",
            "ग": "g", "घ": "gh", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
            "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t",
            "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "ph",
            "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l",
            "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ा": "a",
            "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai",
            "ो": "o", "ौ": "au", "्": "", "ं": "n", "ः": "h"
        }
        res = []
        for ch in text:
            res.append(charmap.get(ch, ch))
        return "".join(res).lower()


def normalise_text(text: str) -> str:
    """
    Lowercase, strip punctuation, map spelling variants via hinglish_norm.json.
    """
    if not text:
        return ""

    # Transliterate if Devanagari
    text = transliterate_devanagari_to_roman(text)

    # Lowercase & strip excess punctuation
    text = text.lower()
    cleaned = re.sub(r"[^\w\s]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Apply phrase-level mapping first
    for phrase, canonical in sorted(_HINGLISH_NORM.items(), key=lambda x: len(x[0]), reverse=True):
        if " " in phrase and phrase in cleaned:
            cleaned = re.sub(rf"\b{re.escape(phrase)}\b", canonical, cleaned)

    # Word-level replacement
    words = cleaned.split()
    norm_words = [_HINGLISH_NORM.get(w, w) for w in words]
    return " ".join(norm_words)


def is_phrase_negated(phrase: str, full_text: str, window_size: int = 4) -> bool:
    """
    Window rule: negation words within window_size tokens before or after the phrase.
    Handles 'saans lene mein dikkat nahi' -> True (negated), 'no chest pain' -> True.
    Exempts emergency clauses like 'not stopping', 'not breathing', 'not responding'.
    """
    norm_text = normalise_text(full_text)
    norm_phrase = normalise_text(phrase)

    tokens = norm_text.split()
    phrase_tokens = norm_phrase.split()
    n_p = len(phrase_tokens)

    if n_p == 0:
        return False

    emergency_negation_combos = {
        ("not", "stopping"), ("not", "breathing"), ("not", "responsive"),
        ("not", "responding"), ("not", "stop"), ("not", "feed"), ("not", "feeding"),
        ("not", "drink"), ("not", "drinking"), ("not", "pass"), ("not", "passed"),
        ("not", "speak"), ("not", "talking"), ("not", "urine"), ("not", "been"),
        ("nahi", "ruk"), ("nahi", "aa"), ("nahi", "pi"), ("nahi", "band"),
        ("nahi", "bol"), ("nahi", "de"), ("nahi", "roka"),
        ("nahim", "ruk"), ("nahim", "aa"), ("nahim", "pi"), ("nahim", "band"),
    }

    # Words that start a new clause. A negation word after a clause boundary
    # belongs to a different symptom/verb, not to this red-flag phrase.
    clause_boundaries = {"and", "aur", "aura", "plus", "also", "ki", "lekin", "but",
                         "fir", "phir", "phira", "toh", "or", "ya", "par", "lekin",
                         "zzsepzzz"}

    for i in range(len(tokens) - n_p + 1):
        if tokens[i:i + n_p] == phrase_tokens:
            start_window = max(0, i - window_size)
            end_window = min(len(tokens), i + n_p + window_size)

            # Check preceding tokens (scan backwards; stop at a clause boundary)
            preceding = tokens[start_window:i]
            for idx in range(len(preceding) - 1, -1, -1):
                nw = preceding[idx]
                if nw in clause_boundaries:
                    break
                if nw in NEGATION_WORDS:
                    abs_idx = start_window + idx
                    if abs_idx + 1 < len(tokens) and (nw, tokens[abs_idx + 1]) in emergency_negation_combos:
                        continue
                    return True

            # Check succeeding tokens (stop at a clause boundary)
            succeeding = tokens[i + n_p:end_window]
            for idx, nw in enumerate(succeeding):
                if nw in clause_boundaries:
                    break
                if nw in NEGATION_WORDS:
                    abs_idx = (i + n_p) + idx
                    if abs_idx + 1 < len(tokens) and (nw, tokens[abs_idx + 1]) in emergency_negation_combos:
                        continue
                    return True

            # First occurrence is not negated: stop (a later duplicate occurrence
            # in combined_roman must not leak its negation window into this one).
            return False

    return False


def detect_and_normalise(text: str) -> tuple[str, str, str]:
    """
    Returns: (original_text, normalised_text, detected_language)
    """
    lang = detect_script_and_language(text)
    norm = normalise_text(text)
    return text, norm, lang
