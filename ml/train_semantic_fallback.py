"""Train the local semantic-screen fallback (used only when Groq is unavailable).

For each of the nine official red flags, a binary TF-IDF + LogisticRegression
classifier is trained on:
  positives: redflag_tests.csv rows carrying that flag + emergency paraphrase rows
  negatives: non-emergency rows + emergency rows of OTHER flags
The decision threshold per flag is tuned on the 217-row set (10th percentile of
positive probability => ~0.90 recall on the tuning set). The holdout is never
used here — thresholds are fixed before ml/eval_semantic_screen.py runs.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from app.config import settings
from app.core.language import normalise_text

DATA_DIR = Path(__file__).resolve().parent / "data"
ARTIFACT = settings.ARTIFACTS_DIR / "semantic_fallback.joblib"

TARGET_RECALL = 0.90


def _rows() -> list[dict]:
    rows = []
    with open(DATA_DIR / "redflag_tests.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "text": r["user_input"],
                "care_type": r["care_type"],
                "flags": [x for x in (r["red_flags"] or "").split(";") if x],
            })
    with open(DATA_DIR / "augment_paraphrases.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["care_type"] != "emergency_112":
                rows.append({"text": r["user_input"], "care_type": r["care_type"], "flags": []})
                continue
            flags = [x for x in (r["red_flags"] or "").split(";") if x]
            rows.append({"text": r["user_input"], "care_type": r["care_type"], "flags": flags})
    return rows


def main():
    rows = _rows()
    texts = [normalise_text(r["text"]) for r in rows]

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True)
    X = vec.fit_transform(texts)

    classifiers = {}
    for flag in settings.RED_FLAGS:
        y = [1 if flag in r["flags"] else 0 for r in rows]
        if sum(y) < 5:
            print(f"  {flag}: too few positives ({sum(y)}), skipping")
            continue
        clf = LogisticRegression(C=2.0, class_weight="balanced", max_iter=500, random_state=42)
        clf.fit(X, y)
        probs = clf.predict_proba(X)[:, 1]
        pos_probs = np.sort(probs[np.array(y) == 1])
        # Threshold at the quantile that keeps ~90% recall on the tuning set.
        thr = float(pos_probs[int((1.0 - TARGET_RECALL) * len(pos_probs))])
        classifiers[flag] = {"clf": clf, "threshold": thr}
        print(f"  {flag}: n_pos={sum(y)}, threshold={thr:.3f}")

    joblib.dump({"vectorizer": vec, "classifiers": classifiers}, ARTIFACT)
    print(f"Saved {ARTIFACT}")


if __name__ == "__main__":
    main()
