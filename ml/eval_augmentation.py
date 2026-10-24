"""Before/after evaluation of Groq paraphrase augmentation (TRAINING ONLY).

Metrics reported (all on OFFICIAL validation rows — the augmented rows never
enter a holdout cluster):
  1. Loose-cluster holdout macro-F1 (strict zero-leakage clusters, same as the
     "stress test" in MODEL_COMPARISON.md) — before vs after augmentation.
  2. Classifier-only emergency recall on redflag_tests.csv — before vs after.

Keep the augmentation only if macro-F1 does not drop AND emergency recall
improves (per the project rule).
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, recall_score

from app.core.language import normalise_text
from ml.compare_models import load_official_dataset, build_loose_topic_groups
from sklearn.metrics.pairwise import cosine_similarity
import scipy.sparse as sp

DATA_DIR = Path(__file__).resolve().parent / "data"
AUG_FILE = DATA_DIR / "augment_paraphrases.csv"
REDFLAG_FILE = DATA_DIR / "redflag_tests.csv"

CARE_TYPES = ["paramedic_home_visit", "home_nursing", "lab_test_home",
              "teleconsultation", "emergency_112"]

DUP_SIM = 0.50  # char-TF-IDF cosine above this = near-duplicate (leakage)


def _train_predict(train_rows, val_rows):
    vec = TfidfVectorizer(ngram_range=(2, 5), analyzer="char", min_df=1, sublinear_tf=True)
    X_tr = vec.fit_transform([r["norm"] for r in train_rows])
    X_val = vec.transform([r["norm"] for r in val_rows])
    clf = LogisticRegression(C=2.0, class_weight="balanced", max_iter=500, random_state=42)
    clf.fit(X_tr, [r["care_type"] for r in train_rows])
    return clf.predict(X_val)


def loose_cluster_holdout(official_rows, aug_rows) -> float:
    """Leave-one-loose-cluster-out macro-F1 (clusters built on OFFICIAL rows only).

    Augmented rows that are near-duplicates of the HELD-OUT cluster are excluded
    from training for that cluster (they are paraphrases of the held-out rows,
    i.e. leakage).
    """
    texts = [r["norm"] for r in official_rows]
    labels = [r["care_type"] for r in official_rows]
    tfidf_pre = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), sublinear_tf=True)
    tf_feats = tfidf_pre.fit_transform(texts)
    groups = build_loose_topic_groups(texts, labels, tf_feats, distance_threshold=0.80)

    aug_feats = None
    if aug_rows:
        aug_feats = tfidf_pre.transform([r["norm"] for r in aug_rows])

    y_true, y_pred = [], []
    for gid in np.unique(groups):
        val_idx = np.where(groups == gid)[0]
        tr_idx = np.where(groups != gid)[0]
        val_rows = [official_rows[i] for i in val_idx]
        tr_rows = [official_rows[i] for i in tr_idx]

        if aug_rows and aug_feats is not None:
            # Drop paraphrase rows that leak the held-out cluster.
            sim = cosine_similarity(aug_feats, tf_feats[val_idx])
            leak_mask = np.max(sim, axis=1) >= DUP_SIM
            clean_aug = [r for r, leak in zip(aug_rows, leak_mask) if not leak]
            tr_rows = tr_rows + clean_aug

        preds = _train_predict(tr_rows, val_rows)
        y_true.extend(r["care_type"] for r in val_rows)
        y_pred.extend(preds)
    return float(f1_score(y_true, y_pred, average="macro", zero_division=0))


def classifier_emergency_recall(train_rows, emergency_rows) -> float:
    """Classifier-only emergency_112 recall (no rule layer)."""
    preds = _train_predict(train_rows, emergency_rows)
    y_true = ["emergency_112"] * len(emergency_rows)
    return float(recall_score(
        [1 if y == "emergency_112" else 0 for y in y_true],
        [1 if p == "emergency_112" else 0 for p in preds],
        zero_division=0,
    ))


def unseen_macro_f1(train_rows, unseen_rows) -> float:
    """Macro-F1 on the independent handwritten unseen_tests.csv (no augmentation overlap)."""
    preds = _train_predict(train_rows, unseen_rows)
    return float(f1_score([r["care_type"] for r in unseen_rows], preds,
                          average="macro", zero_division=0))


def load_unseen() -> list[dict]:
    rows = []
    with open(DATA_DIR / "unseen_tests.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"norm": normalise_text(r["user_input"]), "care_type": r["care_type"]})
    return rows


def main():
    clf_entries, _ = load_official_dataset()
    official_rows = [{
        "norm": e["norm_text"],
        "care_type": e["care_type"],
        "language": e["language"],
    } for e in clf_entries]

    aug_rows = []
    with open(AUG_FILE, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["care_type"] in CARE_TYPES:
                aug_rows.append({"norm": normalise_text(r["user_input"]), "care_type": r["care_type"]})

    emergency_rows = []
    with open(REDFLAG_FILE, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["care_type"] == "emergency_112":
                emergency_rows.append({"norm": normalise_text(r["user_input"]),
                                       "care_type": "emergency_112"})

    print(f"Official labeled rows: {len(official_rows)} | Augmented rows: {len(aug_rows)} | "
          f"Emergency rows (redflag_tests): {len(emergency_rows)}")

    print("\nEvaluating WITHOUT augmentation...")
    f1_before = loose_cluster_holdout(official_rows, [])
    em_before = classifier_emergency_recall(official_rows, emergency_rows)
    unseen_rows = load_unseen()
    uns_before = unseen_macro_f1(official_rows, unseen_rows)
    print(f"  Loose-cluster holdout macro-F1 (before): {f1_before:.4f}")
    print(f"  Classifier-only emergency recall (before): {em_before:.4f}")
    print(f"  Unseen_tests macro-F1 (before, independent set): {uns_before:.4f}")

    print("\nEvaluating WITH augmentation (training only)...")
    f1_after = loose_cluster_holdout(official_rows, aug_rows)
    em_after = classifier_emergency_recall(official_rows + aug_rows, emergency_rows)
    uns_after = unseen_macro_f1(official_rows + aug_rows, unseen_rows)
    print(f"  Loose-cluster holdout macro-F1 (after, leaky): {f1_after:.4f}")
    print(f"  Classifier-only emergency recall (after): {em_after:.4f}")
    print(f"  Unseen_tests macro-F1 (after, independent set): {uns_after:.4f}")

    print("\n" + "=" * 60)
    keep = (uns_after >= uns_before - 1e-9) and (em_after > em_before + 1e-9)
    print(f"Unseen_tests macro-F1 (CLEAN): {uns_before:.4f} -> {uns_after:.4f} ({uns_after - uns_before:+.4f})")
    print(f"Emergency recall: {em_before:.4f} -> {em_after:.4f} ({em_after - em_before:+.4f})")
    print(f"KEEP augmentation? {'YES' if keep else 'NO'} "
          f"(keep iff macro-F1 does not drop AND emergency recall improves)")
    print("=" * 60)

    result = {
        "loose_cluster_macro_f1_before": f1_before,
        "loose_cluster_macro_f1_after_leaky": f1_after,
        "unseen_macro_f1_before": uns_before,
        "unseen_macro_f1_after": uns_after,
        "classifier_emergency_recall_before": em_before,
        "classifier_emergency_recall_after": em_after,
        "keep_augmentation": bool(keep),
        "augmented_rows": len(aug_rows),
        "note": "Loose-cluster 'after' is contaminated: paraphrases were generated from "
                "the WHOLE official dataset (not per-fold training texts), so meaning-level "
                "leakage remains despite the 0.50 wording-similarity filter. The clean "
                "comparison is unseen_tests macro-F1 (independent handwritten set).",
    }
    out = Path(__file__).resolve().parent / "results" / "augmentation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    out.write_text(_json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
