"""TASK B1 — MMCQS vocabulary mining for the Hinglish normaliser.

Extracts frequent symptom / body-part / service words and spelling variants from
the MMCQS code-mixed Hindi-English text and writes HUMAN-REVIEW candidates to
ml/external/hinglish_candidates.csv (columns: variant, suggested_canonical, count).

We do NOT auto-merge into app/data/hinglish_norm.json. Use mmcqs_merge.py to merge
only the rows marked approved=yes.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

RAW_DIR = Path(__file__).resolve().parent / "raw"
OUT_CSV = Path(__file__).resolve().parent / "hinglish_candidates.csv"

# Canonical medical concepts we care about (symptom / body-part / service words).
CANONICAL_TERMS = {
    "headache", "fever", "cough", "chest pain", "breathlessness", "stomach pain",
    "vomiting", "diarrhea", "nausea", "dizziness", "weakness", "fatigue", "rash",
    "itching", "injury", "wound", "sprain", "fracture", "sore throat", "diabetes",
    "hypertension", "swelling", "pain", "bleeding", "urine", "skin", "eye", "ear",
    "teeth", "throat", "stomach", "tonsils", "injection", "dressing", "surgery",
    "blood test", "checkup", "medicine", "pregnant", "fever", "cold",
}

# Known good variants already in the normaliser (to avoid re-suggesting them).
import app.data  # noqa: F401  (ensures app is importable)
from app.core.language import _HINGLISH_NORM

STOPWORDS = {
    "hai", "ho", "raha", "rahi", "rahe", "ko", "se", "aur", "nahi", "nahin", "bhi",
    "mein", "me", "ka", "ki", "ke", "kya", "toh", "bohot", "bahut", "mera", "meri",
    "mere", "mujhe", "kya", "tha", "thi", "the", "main", "yeh", "ye", "ab", "phir",
    "bhi", "hi", "par", "per", "lekin", "karke", "kar", "hona", "ho", "lag", "raha",
    "doctor", "please", "the", "a", "an", "and", "for", "with", "from", "this", "that",
}


def _load_queries() -> list[str]:
    path = RAW_DIR / "mmcqs_hf.jsonl"
    queries = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    queries.append(json.loads(line).get("Codemixed_Question", ""))
    if not queries:
        sample = RAW_DIR / "mmcqs_sample.csv"
        if sample.exists():
            with open(sample, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    queries.append(row.get("Codemixed_Question", ""))
    return [q for q in queries if q and q.strip()]


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [w for w in text.split() if len(w) >= 3 and w not in STOPWORDS]


def _suggest(token: str) -> str | None:
    if token in _HINGLISH_NORM or token in CANONICAL_TERMS:
        return None
    # Close match to an existing normaliser key or canonical term.
    candidates = list(_HINGLISH_NORM.keys()) + list(CANONICAL_TERMS)
    best = None
    best_ratio = 0.0
    for c in candidates:
        if " " in c:
            continue
        ratio = SequenceMatcher(None, token, c).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = c
    if best and best_ratio >= 0.9:
        return _HINGLISH_NORM.get(best, best)
    return None


def mine_vocabulary(top_n: int = 300) -> list[tuple[str, str, int]]:
    queries = _load_queries()
    counts: Counter = Counter()
    for q in queries:
        for tok in _tokenize(q):
            counts[tok] += 1

    rows = []
    for token, count in counts.most_common():
        canon = _suggest(token)
        if canon and canon != token:
            rows.append((token, canon, count))
        if len(rows) >= top_n:
            break
    return rows


def main() -> None:
    rows = mine_vocabulary()
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["variant", "suggested_canonical", "count", "approved", "human_label"])
        for variant, canon, count in rows:
            writer.writerow([variant, canon, count, "", ""])
    print(f"Wrote {len(rows)} candidate rows to {OUT_CSV}")
    print("Review and set approved=yes on rows to keep; then run mmcqs_merge.py.")


if __name__ == "__main__":
    main()
