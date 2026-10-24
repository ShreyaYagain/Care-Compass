"""Train the ML red-flag model (multi-label: one binary classifier per flag).

Candidates (both saved):
  - TF-IDF char n-grams (2-5) + LogisticRegression  -> redflag_model.joblib
    (production default: fast, deterministic, no heavy embeddings at serving)
  - multilingual-e5-small embedding + LogisticRegression -> redflag_model_e5.joblib
    (comparison candidate; the embedding model is reloaded at eval time)

Data (never the holdout redflag_holdout.csv):
  - redflag_tests.csv (positives with red_flags labels)
  - augment_paraphrases.csv (synthetic paraphrases)
  - redflag_negatives_v2.csv (negative examples)
  - train.csv and official/triage_dataset_flat.csv (official labelled data)

Thresholds are chosen on a validation split for recall >= 0.90. Logistic
Regression's predict_proba is already a (sigmoid/Platt) calibrated probability;
we record the threshold per flag and expose it to the runtime so the model and
the deterministic rules decide together.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from app.config import settings
from app.core.language import normalise_text

DATA_DIR = Path(__file__).resolve().parent / "data"
TFIDF_ARTIFACT = settings.ARTIFACTS_DIR / "redflag_model.joblib"
E5_ARTIFACT = settings.ARTIFACTS_DIR / "redflag_model_e5.joblib"

TARGET_RECALL = 0.90
VALIDATION_SIZE = 0.20
RANDOM_STATE = 42


def _csv_rows(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_rows() -> list[dict]:
    """Returns [{text, flags}] over the union of the training sources."""
    rows: list[dict] = []

    for r in _csv_rows(DATA_DIR / "redflag_tests.csv"):
        rows.append({"text": r["user_input"], "flags": _flags(r.get("red_flags"))})

    for r in _csv_rows(DATA_DIR / "augment_paraphrases.csv"):
        rows.append({"text": r["user_input"], "flags": _flags(r.get("red_flags"))})

    for r in _csv_rows(DATA_DIR / "redflag_negatives_v2.csv"):
        rows.append({"text": r["user_input"], "flags": []})

    for r in _csv_rows(DATA_DIR / "train.csv"):
        rows.append({"text": r["user_input"], "flags": _flags(r.get("red_flags"))})

    flat = DATA_DIR / "official" / "triage_dataset_flat.csv"
    if flat.exists():
        for r in _csv_rows(flat):
            rows.append({"text": r["user_input"], "flags": _flags(r.get("red_flags"))})

    # Dedupe by normalised text, keeping the first flags.
    seen: dict[str, list[str]] = {}
    for r in rows:
        key = normalise_text(r["text"])
        if key and key not in seen:
            seen[key] = r["flags"]
    return [{"text": t, "flags": f} for t, f in seen.items()]


def _flags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(";") if x.strip() and x.strip() in settings.RED_FLAGS]


def _fit_thresholds(clf, X, y) -> float:
    """Pick a per-flag threshold on the validation set for recall >= TARGET_RECALL."""
    if sum(y) == 0:
        return 0.999
    probs = clf.predict_proba(X)[:, 1]
    pos = np.sort(probs[np.array(y) == 1])
    idx = int((1.0 - TARGET_RECALL) * len(pos))
    idx = max(0, min(idx, len(pos) - 1))
    return float(pos[idx])


def _train_tfidf(rows: list[dict]):
    texts = [normalise_text(r["text"]) for r in rows]
    y_matrix = {flag: np.array([1 if flag in r["flags"] else 0 for r in rows]) for flag in settings.RED_FLAGS}

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True)
    X = vec.fit_transform(texts)

    classifiers = {}
    for flag in settings.RED_FLAGS:
        y = y_matrix[flag]
        n_pos = int(y.sum())
        if n_pos < 5:
            print(f"  tfidf {flag}: too few positives ({n_pos}), skipping")
            continue
        clf = LogisticRegression(C=2.0, class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
        try:
            X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=VALIDATION_SIZE, stratify=y, random_state=RANDOM_STATE)
        except ValueError:
            X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=VALIDATION_SIZE, random_state=RANDOM_STATE)
        clf.fit(X_tr, y_tr)
        thr = _fit_thresholds(clf, X_va, y_va)
        classifiers[flag] = {"clf": clf, "threshold": thr}
        print(f"  tfidf {flag}: n_pos={n_pos}, threshold={thr:.3f}")

    return {"vectorizer": vec, "classifiers": classifiers, "kind": "tfidf_char_lr"}


def _train_e5(rows: list[dict]):
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("intfloat/multilingual-e5-small")
    texts = [normalise_text(r["text"]) for r in rows]
    # e5 queries should be prefixed with "query: " (short-text retrieval).
    emb = model.encode(["query: " + t for t in texts], normalize_embeddings=True)
    X = np.asarray(emb, dtype=np.float32)

    classifiers = {}
    for flag in settings.RED_FLAGS:
        y = np.array([1 if flag in r["flags"] else 0 for r in rows])
        n_pos = int(y.sum())
        if n_pos < 5:
            print(f"  e5 {flag}: too few positives ({n_pos}), skipping")
            continue
        clf = LogisticRegression(C=2.0, class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
        try:
            X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=VALIDATION_SIZE, stratify=y, random_state=RANDOM_STATE)
        except ValueError:
            X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=VALIDATION_SIZE, random_state=RANDOM_STATE)
        clf.fit(X_tr, y_tr)
        thr = _fit_thresholds(clf, X_va, y_va)
        classifiers[flag] = {"clf": clf, "threshold": thr}
        print(f"  e5 {flag}: n_pos={n_pos}, threshold={thr:.3f}")

    return {"model_name": "intfloat/multilingual-e5-small", "classifiers": classifiers, "kind": "e5_small_lr"}


def main():
    rows = _load_rows()
    print(f"Loaded {len(rows)} unique training rows")

    print("Training TF-IDF + LR ...")
    tfidf = _train_tfidf(rows)
    joblib.dump(tfidf, TFIDF_ARTIFACT)
    print(f"Saved {TFIDF_ARTIFACT}")

    print("Training multilingual-e5-small + LR ...")
    e5 = _train_e5(rows)
    joblib.dump(e5, E5_ARTIFACT)
    print(f"Saved {E5_ARTIFACT}")


if __name__ == "__main__":
    main()
