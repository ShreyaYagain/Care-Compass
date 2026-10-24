"""TASK B3 — build short MMCQS query->summary few-shot examples.

Selects the 30 shortest, cleanest query->summary pairs (each summary under 40
words) to use as few-shot examples for the Groq extraction prompt. Writes to
ml/external/mmcqs_fewshot.json (gitignored — MMCQS text is not redistributed).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

RAW_DIR = Path(__file__).resolve().parent / "raw"
OUT = Path(__file__).resolve().parent / "mmcqs_fewshot.json"

MAX_EXAMPLES = 30
MAX_WORDS = 40


def _load_pairs() -> list[tuple[str, str]]:
    pairs = []
    path = RAW_DIR / "mmcqs_hf.jsonl"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                q = r.get("Codemixed_Question", "")
                s = r.get("summary", "")
                if q and s:
                    pairs.append((q, s))
    if not pairs:
        sample = RAW_DIR / "mmcqs_sample.csv"
        if sample.exists():
            with open(sample, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    pairs.append((row.get("Codemixed_Question", ""), row.get("Question_Summ_Updates", "")))
    return pairs


def main() -> None:
    pairs = _load_pairs()
    # Clean: strip the image-description suffix that some summaries carry.
    cleaned = []
    for q, s in pairs:
        s = s.split("The image shows")[0].strip().rstrip("?").strip()
        s = s.replace("Summary:", "").strip()
        if s and len(s.split()) <= MAX_WORDS and len(q.split()) <= 120:
            cleaned.append({"query": q, "summary": s})
    # Prefer shortest summaries, then shortest queries.
    cleaned.sort(key=lambda p: (len(p["summary"].split()), len(p["query"].split())))
    examples = cleaned[:MAX_EXAMPLES]
    OUT.write_text(json.dumps(examples, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(examples)} few-shot examples to {OUT}")


if __name__ == "__main__":
    main()
