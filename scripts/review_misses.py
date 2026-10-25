#!/usr/bin/env python3
"""Review the intake miss log and propose lexicon entries for a human to approve.

Reads ml/results/lexicon_misses.jsonl (appended by the intake resolver for every
message the lexicon failed on; each record is masked and carries NO session id):

    {"text": "<masked message>", "resolved_by": "embedding|llm|llm_failed|buttons",
     "resolved_symptom": "<canonical|None>", "created_at": "<iso>"}

Groups frequent (normalised) misses and, for each group, proposes candidate
lexicon synonym entries derived from the raw message. It NEVER auto-adds:
proposals are printed for a human to review and add to
app/data/symptoms.yaml (or app/data/hinglish_norm.json) manually.

Usage:
    python scripts/review_misses.py [--top N] [--min-count M]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from app.core.language import normalise_text

BASE_DIR = Path(__file__).resolve().parent.parent
MISS_LOG = BASE_DIR / "ml" / "results" / "lexicon_misses.jsonl"


def load_misses() -> list[dict]:
    if not MISS_LOG.exists():
        return []
    rows = []
    with open(MISS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _stopwords() -> set[str]:
    return {
        "mujhe", "mere", "mera", "meri", "hai", "hain", "ho", "raha", "rahi",
        "rahe", "ko", "se", "me", "mein", "aur", "bhi", "bohot", "bahut",
        "thoda", "halka", "halki", "yaar", "lol", "bro", "plz", "please",
        "the", "a", "an", "my", "i", "have", "is", "are", "to", "do", "din",
        "kal", "subah", "se", "ke", "ki", "ka", "na", "nahi", "abhi", "bahut",
        "zyada", "bhot", "ho", "gaya", "gayi", "karo", "karna", "chahiye",
    }


def _candidate_tokens(text: str) -> list[str]:
    norm = normalise_text(text)
    tokens = re.findall(r"[a-z]+", norm)
    sw = _stopwords()
    return [t for t in tokens if t not in sw and len(t) >= 4]


def propose(rows: list[dict], top: int = 30, min_count: int = 2) -> list[dict]:
    groups: Counter[str] = Counter()
    by_resolver: dict[str, Counter[str]] = {}
    for r in rows:
        text = r.get("text", "")
        norm = normalise_text(text)
        if not norm:
            continue
        groups[norm] += 1
        resolver = r.get("resolved_by", "unknown")
        by_resolver.setdefault(resolver, Counter())[norm] += 1

    proposals = []
    for norm, count in groups.most_common(top):
        if count < min_count:
            continue
        # Recover the original text for one example per group.
        example = next((r["text"] for r in rows if normalise_text(r.get("text", "")) == norm), norm)
        candidates = _candidate_tokens(example)
        # Resolver distribution for this group.
        resolvers = {k: c[norm] for k, c in by_resolver.items() if c.get(norm)}
        proposals.append({
            "normalised": norm,
            "example": example,
            "count": count,
            "resolved_by": resolvers,
            "candidate_synonyms": candidates,
        })
    return proposals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--min-count", type=int, default=2)
    args = parser.parse_args()

    rows = load_misses()
    if not rows:
        print(f"No miss log at {MISS_LOG} (no messages have missed the lexicon yet).")
        return

    total = len(rows)
    resolvers = Counter(r.get("resolved_by", "unknown") for r in rows)
    print(f"{total} lexicon misses in {MISS_LOG}")
    print(f"Resolver distribution: {dict(resolvers)}")
    print()

    proposals = propose(rows, top=args.top, min_count=args.min_count)
    if not proposals:
        print("No groups meet the min-count threshold.")
        return

    print(f"{'count':>6}  {'resolved_by':<28}  normalised message -> candidate synonyms")
    print("-" * 100)
    for p in proposals:
        res = ", ".join(f"{k}={v}" for k, v in p["resolved_by"].items())
        syns = ", ".join(f'"{s}"' for s in p["candidate_synonyms"])
        print(f"{p['count']:>6}  {res:<28}  {p['normalised']}  ->  {syns}")

    print()
    print("ACTION: review the candidates above and add the ones that are real")
    print("symptom synonyms to app/data/symptoms.yaml (or app/data/hinglish_norm.json)")
    print("MANUALLY. This script never writes to the lexicon.")


if __name__ == "__main__":
    main()
