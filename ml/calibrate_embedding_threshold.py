#!/usr/bin/env python3
"""Calibrate the open-vocabulary embedding-match threshold on the TRAINING split.

The intake resolver's step-2 embedding match (multilingual-e5-small) maps a
message to the nearest lexicon symptom. This script measures, on ml/data/train.csv
(the training split only — never redflag_holdout.csv or unseen_tests.csv), the
cosine-similarity distribution of:
  - CORRECT matches (argmax symptom == the lexicon's symptom for that text)
  - WRONG matches   (argmax symptom != the lexicon's symptom)
and also reports where pure noise lands, so the threshold is chosen transparently.

It prints a recommended threshold and rationale. It never tunes anything on the
holdout / unseen sets.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.core.intake import rule_based_extract
from app.core.language import normalise_text
from app.core.open_vocab import _symptom_index, _load_embedder

NOISE = ["blah blah", "zzzz", "what is the weather", "asdf", "qwerty", "12345"]


def main() -> int:
    labels, canon, embs = _symptom_index()
    model = _load_embedder()

    correct = []
    wrong = []
    hit = total = 0
    for r in csv.DictReader(open(Path(__file__).resolve().parent / "data" / "train.csv")):
        text = r["user_input"]
        syms = [s for s in (rule_based_extract(normalise_text(text), []).get("symptoms") or [])
                if s in set(canon)]
        if not syms:
            continue
        q = model.encode(["query: " + text], normalize_embeddings=True)[0]
        sims = np.asarray(embs) @ q
        i = int(np.argmax(sims))
        total += 1
        if canon[i] in syms:
            hit += 1
            correct.append(float(sims[i]))
        else:
            wrong.append(float(sims[i]))

    correct = np.array(correct) if correct else np.array([0.0])
    wrong = np.array(wrong) if wrong else np.array([0.0])
    print(f"training rows with a lexicon symptom: {total}")
    print(f"argmax-correct (nearest symptom is right): {hit}/{total} = {hit/total:.3f}")
    print(f"correct-match score: median={np.median(correct):.3f} p5={np.percentile(correct, 5):.3f} min={correct.min():.3f}")
    print(f"wrong-match score:   median={np.median(wrong):.3f} max={wrong.max():.3f}")

    # Where does pure noise land?
    noise_scores = []
    for t in NOISE:
        q = model.encode(["query: " + t], normalize_embeddings=True)[0]
        sims = np.asarray(embs) @ q
        noise_scores.append(float(sims.max()))
    print(f"noise max-similarity: {[round(s, 3) for s in noise_scores]}")

    # Recommend a threshold just above the wrong-match max (high precision).
    rec = max(wrong.max() + 0.005, 0.80)
    print()
    print(f"recommended high-precision threshold: {rec:.3f} "
          f"(rejects wrong matches up to {wrong.max():.3f}, keeps correct median {np.median(correct):.3f})")
    print("NOTE: pure noise reaches ~0.85, overlapping correct matches; the embedding")
    print("step is a conservative safety net — the DeepSeek mapper + buttons are the")
    print("primary open-vocabulary resolvers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
