"""Regenerate model plots (confusion matrix + reliability) from exact-text
grouped cross-validation (out-of-fold only, calibration inside each fold).

Strict rules enforced here:
  - NO LLM calls. Slots come from the deterministic lexicon
    (rule_based_extract) only; the classifier feature is the production input
    build_classifier_text(slots, norm_text) = canonical symptoms + validated
    slots + raw normalised text.
  - NO tuning on holdouts. The only hyper-parameters are the production fixed
    config (TF-IDF char 2-5, sublinear_tf, LogisticRegression C=2.0 balanced).
  - Exact-text grouping: every text and all its duplicates stay in the same
    fold (StratifiedGroupKFold on the normalised text).
  - Calibration is fitted inside each training fold, with the calibration CV
    also grouped by exact text (so duplicates never straddle a calibration
    split). A non-grouped calibration variant is run too, only to test the
    "duplicates in calibration folds collapse probabilities" hypothesis.

Outputs:
  - ml/results/oof_predictions.csv   (row id, text hash, true label, 5 probs)
  - docs/figures/confusion_grouped_cv_oof.png
  - docs/figures/reliability_emergency_oof.png
  - docs/figures/reliability_per_class_oof.png
  - docs/figures/confusion_unseen.png / confusion_redflag_holdout.png
  - docs/figures/confusion_pipeline_oof.png (full pipeline, cached LLM only)
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

# Ensure no live LLM is ever reachable from this script.
os.environ.pop("DEEPSEEK_API_KEY", None)
os.environ.pop("GROQ_API_KEY", None)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, confusion_matrix
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold, StratifiedKFold

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.core.intake import rule_based_extract, build_classifier_text
from app.core.language import normalise_text

DATA_DIR = ROOT / "ml" / "data"
RESULTS_DIR = ROOT / "ml" / "results"
FIGURES_DIR = ROOT / "docs" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

OFFICIAL = DATA_DIR / "official" / "triage_dataset.jsonl"
UNSEEN = DATA_DIR / "unseen_tests.csv"
REDFLAG_HOLDOUT = DATA_DIR / "redflag_holdout.csv"

CARE_TYPES = settings.CARE_TYPES  # production order

# Production fixed hyper-parameters (never tuned on holdouts).
TFIDF_KW = dict(ngram_range=(2, 5), analyzer="char", min_df=1, sublinear_tf=True)
LR_KW = dict(C=2.0, class_weight="balanced", max_iter=500, random_state=42)


def _text_hash(raw_text: str) -> str:
    return hashlib.sha256((raw_text or "").encode("utf-8")).hexdigest()[:16]


def load_official():
    rows = []
    with open(OFFICIAL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            req = item.get("request", {})
            resp = item.get("response", {})
            u = (req.get("user_input") or "").strip()
            norm = normalise_text(u)
            ct = resp.get("care_type")
            if not norm or ct is None:
                continue
            rows.append({
                "id": item.get("id") or "",
                "raw_text": u,
                "norm_text": norm,
                "care_type": ct,
                "language": item.get("detected_language") or req.get("language") or "en",
            })
    return rows


def featurize(rows):
    feats = []
    for r in rows:
        slots = rule_based_extract(r["norm_text"])
        feats.append(build_classifier_text(slots, r["norm_text"]))
    return feats


def _calibrated_fit(X_tr, y_tr, groups_tr, grouped: bool):
    """Fit TF-IDF already applied outside; returns a fitted calibrated model.
    grouped=True groups the calibration CV by exact text."""
    base = LogisticRegression(**LR_KW)
    n_uniq = len(np.unique(groups_tr))
    if grouped and n_uniq >= 2:
        n_splits = min(3, n_uniq)
        gkf = GroupKFold(n_splits=n_splits)
        cv_splits = [(tr, va) for tr, va in gkf.split(X_tr, y_tr, groups=groups_tr)]
        clf = CalibratedClassifierCV(base, method="sigmoid", cv=cv_splits)
    else:
        clf = CalibratedClassifierCV(base, method="sigmoid", cv=3)
    clf.fit(X_tr, y_tr)
    return clf


def grouped_oof(rows, grouped_calibration: bool = True):
    """Exact-text grouped 5-fold CV -> out-of-fold class probabilities."""
    feats = featurize(rows)
    labels = [r["care_type"] for r in rows]
    groups = np.array([r["norm_text"] for r in rows])

    sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    splits = list(sgkf.split(feats, labels, groups=groups))

    # Accumulate OOF probabilities in production CARE_TYPES order.
    n = len(rows)
    probs_oof = np.zeros((n, len(CARE_TYPES)))
    preds = []
    for tr, va in splits:
        vec = TfidfVectorizer(**TFIDF_KW)
        X_tr = vec.fit_transform([feats[i] for i in tr])
        X_va = vec.transform([feats[i] for i in va])
        y_tr = [labels[i] for i in tr]
        clf = _calibrated_fit(X_tr, y_tr, groups[tr], grouped=grouped_calibration)
        p = clf.predict_proba(X_va)
        classes = list(clf.classes_)
        for k, i in enumerate(va):
            for ci, c in enumerate(classes):
                if c in CARE_TYPES:
                    probs_oof[i, CARE_TYPES.index(c)] = float(p[k, ci])
            preds.append((i, classes[int(np.argmax(p[k]))]))

    y_pred = [None] * n
    for i, c in preds:
        y_pred[i] = c
    return labels, y_pred, probs_oof


def save_oof_csv(rows, labels, probs_oof, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row_id", "text_hash", "true_label"] + [f"P({c})" for c in CARE_TYPES])
        for i, r in enumerate(rows):
            w.writerow([r["id"], _text_hash(r["raw_text"]), labels[i]] + [round(float(x), 6) for x in probs_oof[i]])
    print(f"Saved OOF predictions -> {path}")


# ---------------------------------------------------------------------------
# Confusion matrix plots
# ---------------------------------------------------------------------------

def plot_confusion(y_true, y_pred, classes, title, path, normalize=None, extra_cols=None):
    """normalize='true' -> row-normalised. extra_cols: list of extra column labels
    (e.g. ['follow-up']) appended to the predicted axis."""
    col_labels = list(classes) + (extra_cols or [])
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    if extra_cols:
        cm = np.hstack([cm, np.zeros((len(classes), len(extra_cols)), dtype=int)])
    if normalize == "true":
        sums = cm.sum(axis=1, keepdims=True)
        cm_plot = cm / np.where(sums == 0, 1, sums)
        fmt = ".2f"
    else:
        cm_plot = cm
        fmt = "d"

    fig, ax = plt.subplots(figsize=(max(6, 1.4 * len(col_labels)), 5))
    im = ax.imshow(cm_plot, interpolation="nearest", cmap=plt.cm.Blues)
    ax.set_title(title, fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    tick_marks = np.arange(len(col_labels))
    ax.set_xticks(tick_marks)
    ax.set_xticklabels([c.replace("_", "\n") for c in col_labels], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(np.arange(len(classes)))
    ax.set_yticklabels([c.replace("_", " ") for c in classes], fontsize=8)
    thresh = cm_plot.max() / 2.0 if cm_plot.max() > 0 else 0.5
    for i in range(len(classes)):
        for j in range(len(col_labels)):
            ax.text(j, i, format(cm_plot[i, j], fmt), ha="center", va="center",
                    color="white" if cm_plot[i, j] > thresh else "black", fontsize=8)
    ax.set_ylabel("True Label")
    ax.set_xlabel("Predicted Label")
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")
    return cm


def plot_confusion_dual(y_true, y_pred, classes, title, path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    cm_norm = cm / np.where(cm.sum(axis=1, keepdims=True) == 0, 1, cm.sum(axis=1, keepdims=True))
    for ax, cm_plot, fmt, sub in (
        (axes[0], cm, "d", "Counts"),
        (axes[1], cm_norm, ".2f", "Row-normalised"),
    ):
        im = ax.imshow(cm_plot, interpolation="nearest", cmap=plt.cm.Blues)
        ax.set_title(f"{sub}", fontsize=10)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        tick_marks = np.arange(len(classes))
        ax.set_xticks(tick_marks)
        ax.set_xticklabels([c.replace("_", "\n") for c in classes], rotation=45, ha="right", fontsize=8)
        ax.set_yticks(tick_marks)
        ax.set_yticklabels([c.replace("_", " ") for c in classes], fontsize=8)
        thresh = cm_plot.max() / 2.0 if cm_plot.max() > 0 else 0.5
        for i in range(len(classes)):
            for j in range(len(classes)):
                ax.text(j, i, format(cm_plot[i, j], fmt), ha="center", va="center",
                        color="white" if cm_plot[i, j] > thresh else "black", fontsize=8)
        ax.set_ylabel("True Label")
        ax.set_xlabel("Predicted Label")
    fig.suptitle(title, fontsize=11)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")
    return cm


# ---------------------------------------------------------------------------
# Reliability / calibration
# ---------------------------------------------------------------------------

def ece_quantile(y_true, p, n_bins=10):
    """Expected calibration error with equal-frequency (quantile) bins."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    y_s, p_s = y[order], p[order]
    bin_edges = np.linspace(0, len(y_s), n_bins + 1).astype(int)
    ece = 0.0
    n = len(y_s)
    for a, b in zip(bin_edges[:-1], bin_edges[1:]):
        if b <= a:
            continue
        seg_p = p_s[a:b]
        seg_y = y_s[a:b]
        ece += len(seg_p) / n * abs(seg_p.mean() - seg_y.mean())
    return float(ece)


def reliability_bins(y_true, p, n_bins=10):
    """Quantile bins -> (mean_pred, frac_pos, count) with empty bins dropped."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    y_s, p_s = y[order], p[order]
    bin_edges = np.linspace(0, len(y_s), n_bins + 1).astype(int)
    out = []
    for a, b in zip(bin_edges[:-1], bin_edges[1:]):
        if b <= a:
            continue
        seg_p = p_s[a:b]
        seg_y = y_s[a:b]
        out.append((float(seg_p.mean()), float(seg_y.mean()), int(len(seg_p))))
    return out


def plot_reliability(y_true, p, title, path):
    bins = reliability_bins(y_true, p, n_bins=10)
    bins = [b for b in bins if b[2] > 0]  # drop empty
    mp = [b[0] for b in bins]
    fp = [b[1] for b in bins]
    cnt = [b[2] for b in bins]
    ece = ece_quantile(y_true, p, n_bins=10)
    brier = brier_score_loss(y_true, p)

    fig, (ax, axh) = plt.subplots(2, 1, figsize=(7, 7), gridspec_kw={"height_ratios": [2.5, 1]})
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect")
    ax.plot(mp, fp, marker="o", linewidth=2, label="Model A (OOF)")
    # Sample-count labels alternate above/below the point so they never overlap.
    for k, (x, y, c) in enumerate(zip(mp, fp, cnt)):
        off = (0, 7) if k % 2 == 0 else (0, -11)
        ax.annotate(f"n={c}", (x, y), textcoords="offset points", xytext=off,
                    ha="center", fontsize=7, color="0.25")
    ax.set_xlabel("Mean Predicted P(emergency_112)")
    ax.set_ylabel("Fraction of Positives")
    ax.set_title(title + f"\nECE={ece:.4f}   Brier={brier:.4f}", fontsize=9)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, linestyle=":", alpha=0.6)

    axh.hist(p, bins=30, color="steelblue", alpha=0.8)
    axh.set_xlabel("Predicted P(emergency_112)")
    axh.set_ylabel("Count")
    axh.grid(True, linestyle=":", alpha=0.5)
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {path} (ECE={ece:.4f}, Brier={brier:.4f}, bins={len(bins)})")
    return ece, brier, bins


def plot_per_class_reliability(labels, probs_oof, title, path):
    """One-vs-rest reliability for the four non-emergency care types."""
    others = [c for c in CARE_TYPES if c != "emergency_112"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes = axes.ravel()
    for ax, c in zip(axes, others):
        ci = CARE_TYPES.index(c)
        p = probs_oof[:, ci]
        y = (np.array(labels) == c).astype(int)
        bins = [b for b in reliability_bins(y, p, n_bins=10) if b[2] > 0]
        mp = [b[0] for b in bins]
        fp = [b[1] for b in bins]
        ece = ece_quantile(y, p, n_bins=10)
        ax.plot([0, 1], [0, 1], "--", color="gray")
        ax.plot(mp, fp, marker="o", linewidth=2)
        ax.set_title(f"{c.replace('_', ' ')} (ECE={ece:.3f})", fontsize=9)
        ax.set_xlabel("Mean Predicted Probability")
        ax.set_ylabel("Fraction of Positives")
        ax.grid(True, linestyle=":", alpha=0.6)
    fig.suptitle(title, fontsize=11)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ---------------------------------------------------------------------------
# Threshold report
# ---------------------------------------------------------------------------

def threshold_report(labels, probs_oof):
    y = np.array(labels)
    p_em = probs_oof[:, CARE_TYPES.index("emergency_112")]
    y_em = (y == "emergency_112").astype(int)
    pred_em = (p_em >= 0.50).astype(int)
    tp = int(np.sum((pred_em == 1) & (y_em == 1)))
    fp = int(np.sum((pred_em == 1) & (y_em == 0)))
    fn = int(np.sum((pred_em == 0) & (y_em == 1)))
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    mid = int(np.sum((p_em >= 0.30) & (p_em <= 0.70)))
    return {
        "threshold": 0.50, "tp": tp, "fp": fp, "fn": fn,
        "recall": recall, "precision": precision, "n_pos": tp + fn,
        "n_in_030_070": mid,
    }


# ---------------------------------------------------------------------------
# Classifier-only evaluation on holdouts (no LLM)
# ---------------------------------------------------------------------------

def holdout_confusion(csv_path, classes, title, path):
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            u = (row.get("user_input") or "").strip()
            ct = (row.get("care_type") or "").strip()
            if not u or not ct:
                continue
            norm = normalise_text(u)
            slots = rule_based_extract(norm)
            feat = build_classifier_text(slots, norm)
            rows.append({"text": norm, "feat": feat, "care_type": ct})

    # Fit the production model on the full official training set (fixed config),
    # predict on the holdout. This is classifier-only (no LLM, no rules).
    train_rows = load_official()
    train_feats = featurize(train_rows)
    train_labels = [r["care_type"] for r in train_rows]
    vec = TfidfVectorizer(**TFIDF_KW)
    X_tr = vec.fit_transform(train_feats)
    clf = _calibrated_fit(X_tr, train_labels, np.array([r["norm_text"] for r in train_rows]), grouped=True)
    X_te = vec.transform([r["feat"] for r in rows])
    p = clf.predict_proba(X_te)
    cl = list(clf.classes_)
    y_pred = [cl[int(np.argmax(pi))] for pi in p]
    y_true = [r["care_type"] for r in rows]
    cm = plot_confusion_dual(y_true, y_pred, classes, title + f", n={len(rows)}", path)
    return y_true, y_pred, p, cl


def pipeline_confusion(rows, classes, path):
    """Full-pipeline confusion matrix with a 'follow-up' column.

    The LLM is run strictly cache-only: the HTTP transport is replaced so no
    network call is ever made, and the LLM is treated as available so the
    pipeline *attempts* the semantic screen + second opinion; those read the
    on-disk cache and return None on a miss (no live call). Cache hits/misses
    are counted and returned.
    """
    import app.core.llm as llm_mod
    from unittest.mock import patch

    # Treat the LLM as available (so the pipeline attempts the LLM stages), but
    # cut the transport so a cache miss can never reach the network.
    prev_key = settings.DEEPSEEK_API_KEY
    settings.DEEPSEEK_API_KEY = prev_key or "cache-only-placeholder"
    settings.LLM_ROLE = "second_opinion"

    cache_stats = {"hit": 0, "miss": 0}
    _orig_read = llm_mod._read_cache

    def _counting_read(key):
        v = _orig_read(key)
        if v is None:
            cache_stats["miss"] += 1
        else:
            cache_stats["hit"] += 1
        return v

    def _no_network(*args, **kwargs):
        return None, 0

    from app.core.pipeline import run_triage_pipeline
    from app.schemas import TriageRequest, Location

    y_true = []
    y_pred = []  # predicted care_type or 'follow-up'
    with patch.object(llm_mod, "_read_cache", side_effect=_counting_read), \
            patch.object(llm_mod, "_chat_completion", side_effect=_no_network):
        for r in rows:
            try:
                resp = run_triage_pipeline(TriageRequest(
                    user_input=r["raw_text"], language=r["language"], allow_followup=True,
                    context_consent=False, location=Location(lat=28.54, lng=77.27),
                ))
            except Exception:
                settings.DEEPSEEK_API_KEY = prev_key
                raise
            y_true.append(r["care_type"])
            if resp.follow_up_question:
                y_pred.append("follow-up")
            else:
                y_pred.append(resp.care_type or "follow-up")

    settings.DEEPSEEK_API_KEY = prev_key

    # Build 5 x (5+follow-up) confusion matrix.
    col_labels = list(classes) + ["follow-up"]
    cm = np.zeros((len(classes), len(col_labels)), dtype=int)
    for t, p in zip(y_true, y_pred):
        ti = classes.index(t) if t in classes else None
        pi = col_labels.index(p) if p in col_labels else None
        if ti is not None and pi is not None:
            cm[ti, pi] += 1

    fig, ax = plt.subplots(figsize=(9, 6))
    cm_norm = cm / np.where(cm.sum(axis=1, keepdims=True) == 0, 1, cm.sum(axis=1, keepdims=True))
    im = ax.imshow(cm_norm, interpolation="nearest", cmap=plt.cm.Blues)
    ax.set_title(f"Full pipeline, exact-text grouped rows (cached-LLM only), n={len(rows)}", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_xticks(np.arange(len(col_labels)))
    ax.set_xticklabels([c.replace("_", "\n") for c in col_labels], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(np.arange(len(classes)))
    ax.set_yticklabels([c.replace("_", " ") for c in classes], fontsize=8)
    thresh = cm_norm.max() / 2.0 if cm_norm.max() > 0 else 0.5
    for i in range(len(classes)):
        for j in range(len(col_labels)):
            ax.text(j, i, f"{cm[i, j]}\n({cm_norm[i, j]:.2f})", ha="center", va="center",
                    color="white" if cm_norm[i, j] > thresh else "black", fontsize=7)
    ax.set_ylabel("True Label")
    ax.set_xlabel("Predicted (incl. follow-up)")
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved {path} (cache hits={cache_stats['hit']}, misses={cache_stats['miss']})")
    return cm, cache_stats


def main():
    # Belt-and-braces: guarantee no LLM can ever be reached from this script.
    settings.DEEPSEEK_API_KEY = ""
    settings.GROQ_API_KEY = ""
    settings.LLM_ROLE = "off"
    print("=" * 80)
    print("Regenerating plots from exact-text grouped CV (OOF, no LLM)")
    print("=" * 80)

    rows = load_official()
    print(f"Official labelled rows: {len(rows)}")
    print(f"Unique exact texts: {len(set(r['norm_text'] for r in rows))}")
    print(f"Label distribution: {dict(Counter(r['care_type'] for r in rows))}")

    labels, y_pred, probs_oof = grouped_oof(rows, grouped_calibration=True)
    acc = sum(1 for a, b in zip(labels, y_pred) if a == b) / len(labels)
    from sklearn.metrics import f1_score
    macro_f1 = f1_score(labels, y_pred, average="macro", zero_division=0)
    print(f"\n[OOF, exact-text grouped, grouped calibration] accuracy={acc:.4f} macro-F1={macro_f1:.4f}")

    # Also run non-grouped calibration to test the duplicate-in-calibration hypothesis.
    labels_u, y_pred_u, probs_u = grouped_oof(rows, grouped_calibration=False)
    acc_u = sum(1 for a, b in zip(labels_u, y_pred_u) if a == b) / len(labels_u)
    print(f"[OOF, exact-text grouped, NON-grouped calibration] accuracy={acc_u:.4f} "
          f"macro-F1={f1_score(labels_u, y_pred_u, average='macro', zero_division=0):.4f}")

    # 1. Save OOF predictions CSV.
    save_oof_csv(rows, labels, probs_oof, RESULTS_DIR / "oof_predictions.csv")

    # 2a. Classifier-only OOF confusion matrix.
    plot_confusion_dual(
        labels, y_pred, CARE_TYPES,
        "Model A, exact-text grouped CV (out-of-fold), n=%d" % len(rows),
        FIGURES_DIR / "confusion_grouped_cv_oof.png",
    )

    # 3. Reliability diagram for P(emergency_112).
    em_idx = CARE_TYPES.index("emergency_112")
    p_em = probs_oof[:, em_idx]
    y_em = (np.array(labels) == "emergency_112").astype(int)
    ece, brier, bins = plot_reliability(
        y_em, p_em,
        "Reliability: P(emergency_112), exact-text grouped CV (OOF), n=%d" % len(rows),
        FIGURES_DIR / "reliability_emergency_oof.png",
    )

    # 4. Per-class OVR reliability for the other four care types.
    plot_per_class_reliability(
        labels, probs_oof,
        "Per-class one-vs-rest reliability (OOF), n=%d" % len(rows),
        FIGURES_DIR / "reliability_per_class_oof.png",
    )

    # 5. Threshold report.
    tr = threshold_report(labels, probs_oof)
    print("\n[Threshold report at 0.50]")
    print(f"  recall={tr['recall']:.4f}  precision={tr['precision']:.4f}  "
          f"tp={tr['tp']} fp={tr['fp']} fn={tr['fn']}  n_in_[0.30,0.70]={tr['n_in_030_070']}")

    # Probability collapse diagnostics.
    print("\n[Probability collapse diagnostic]")
    for name, p_ in (("grouped-cal", probs_oof), ("ungrouped-cal", probs_u)):
        pe = p_[:, em_idx]
        near_extreme = float(np.mean((pe < 0.05) | (pe > 0.95)))
        print(f"  {name}: P(emergency_112) mean={pe.mean():.3f} "
              f"frac<0.05|>0.95={near_extreme:.3f}  ECE={ece_quantile(y_em, pe, 10):.4f} "
              f"Brier={brier_score_loss(y_em, pe):.4f}")

    # 2c. Holdout confusion matrices (classifier-only, no LLM).
    holdout_confusion(UNSEEN, CARE_TYPES, "Model A, unseen_tests.csv (classifier-only)", FIGURES_DIR / "confusion_unseen.png")
    holdout_confusion(REDFLAG_HOLDOUT, CARE_TYPES, "Model A, redflag_holdout.csv (classifier-only)", FIGURES_DIR / "confusion_redflag_holdout.png")

    # 2b. Full pipeline (cached LLM only) confusion matrix with follow-up column.
    pipeline_cm, cache_stats = pipeline_confusion(rows, CARE_TYPES, FIGURES_DIR / "confusion_pipeline_oof.png")

    print("\nDone. ECE=%.4f Brier=%.4f macro-F1=%.4f acc=%.4f" % (ece, brier, macro_f1, acc))
    return {
        "n": len(rows), "acc": acc, "macro_f1": macro_f1, "ece": ece, "brier": brier,
        "threshold": tr, "pipeline_cache": cache_stats,
    }


if __name__ == "__main__":
    main()
