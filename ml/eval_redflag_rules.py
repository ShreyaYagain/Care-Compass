"""Evaluate the deterministic red-flag rule layer against ml/data/redflag_tests.csv.

Reports:
  - per-flag recall (of the positive rows, was the expected flag detected?)
  - false-alarm rate on negated + near-miss rows
  - Wilson 95% confidence intervals
  - classifier-only emergency recall (TF-IDF+LR, rule layer bypassed)
  - a list of MISSES (positive rows whose flag was not detected) to fix in
    app/data/red_flags.yaml

Outputs docs/DATA_AUDIT.md (rule-layer section) is updated separately.
"""
import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.language import normalise_text
from app.core.red_flags import check_red_flags
from app.config import settings

CSV_PATH = Path(__file__).resolve().parent / "data" / "redflag_tests.csv"

FLAGS = settings.RED_FLAGS


def wilson(p: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def load_rows():
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def rule_flags(text: str) -> tuple[list[str], bool]:
    norm = normalise_text(text)
    high, _, _, is_emergency = check_red_flags(text, norm, return_medium=True)
    return high, is_emergency


def classifier_emergency(text: str) -> bool:
    """Classifier-only emergency_112 decision (no rule layer)."""
    import joblib
    import numpy as np
    vec = joblib.load(settings.ARTIFACTS_DIR / "tfidf_vectorizer.joblib")
    clf = joblib.load(settings.ARTIFACTS_DIR / "triage_care.joblib")
    norm = normalise_text(text)
    x = vec.transform([norm])
    probs = clf.predict_proba(x)[0]
    classes = list(clf.classes_)
    p = dict(zip(classes, probs))
    return p.get("emergency_112", 0.0) >= 0.50


def main():
    rows = load_rows()
    positives = [r for r in rows if r["care_type"] == "emergency_112"]
    negatives = [r for r in rows if r["care_type"] != "emergency_112"]

    # Rule-layer recall per flag (multi-flag rows count toward each listed flag).
    per_flag = {f: {"tp": 0, "total": 0} for f in FLAGS}
    misses = []
    for r in positives:
        expected = set((r["red_flags"] or "").split(";"))
        detected, is_em = rule_flags(r["user_input"])
        for f in expected:
            if f in FLAGS:
                per_flag[f]["total"] += 1
                if f in detected:
                    per_flag[f]["tp"] += 1
        if not expected.issubset(set(detected)):
            misses.append((r["id"], r["user_input"], sorted(expected), detected))

    # False alarms on negated + near-miss.
    false_alarms = []
    for r in negatives:
        _, is_em = rule_flags(r["user_input"])
        if is_em:
            false_alarms.append((r["id"], r["user_input"]))

    n_pos = len(positives)
    n_neg = len(negatives)
    print("=" * 80)
    print("RED-FLAG RULE LAYER EVALUATION")
    print("=" * 80)
    print(f"Positive rows (emergency): {n_pos} | Non-emergency rows: {n_neg}")
    print()
    print(f"{'flag':<22} {'recall':<10} {'tp/total':<10} {'Wilson 95% CI'}")
    for f in FLAGS:
        tp, tot = per_flag[f]["tp"], per_flag[f]["total"]
        rec = tp / tot if tot else 0.0
        lo, hi = wilson(rec, tot)
        print(f"{f:<22} {rec:.3f}     {tp}/{tot:<7} [{lo:.3f}, {hi:.3f}]")

    rule_em_tp = sum(1 for r in positives if rule_flags(r["user_input"])[1])
    rule_recall = rule_em_tp / n_pos if n_pos else 0.0
    fa_rate = len(false_alarms) / n_neg if n_neg else 0.0
    print()
    print(f"Rule-layer overall emergency recall: {rule_recall:.3f} ({rule_em_tp}/{n_pos})")
    print(f"Rule-layer false-alarm rate (non-emergency flagged): {fa_rate:.3f} ({len(false_alarms)}/{n_neg})")

    # Classifier-only recall.
    cls_tp = sum(1 for r in positives if classifier_emergency(r["user_input"]))
    cls_recall = cls_tp / n_pos if n_pos else 0.0
    cls_fa = sum(1 for r in negatives if classifier_emergency(r["user_input"]))
    print(f"Classifier-only emergency recall: {cls_recall:.3f} ({cls_tp}/{n_pos})")
    print(f"Classifier-only false alarms: {cls_fa}/{n_neg}")

    print()
    print(f"MISSES (expected flag not detected): {len(misses)}")
    for mid, text, exp, det in misses:
        print(f"  {mid}: {text!r}  expected={exp} detected={det}")

    print()
    print(f"FALSE ALARMS (non-emergency flagged): {len(false_alarms)}")
    for fid, text in false_alarms:
        print(f"  {fid}: {text!r}")


if __name__ == "__main__":
    main()
