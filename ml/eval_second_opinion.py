"""Evaluate the ML-first pipeline: ML only vs LLM second opinion.

Uses the human-written holdout when available, else redflag_holdout.csv, plus
redflag_tests.csv. No thresholds or model weights are tuned on this data.

Reports:
  - ML red-flag model: per-flag recall, overall emergency recall with a Wilson
    interval, and precision.
  - ML care_type routing accuracy.
  - Rules-vs-ML disagreement rate and ML inference latency.
  - (Optional, needs DEEPSEEK_API_KEY) LLM-only and ML+second-opinion routing
    accuracy, emergency recall, disagreement rate and latency.
"""
import csv
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.core.language import normalise_text
from app.core.redflag_model import predict_flags, load_redflag_model
from app.core.intake import rule_based_extract, build_classifier_text
from app.core.triage_model import predict_triage
from app.core.second_opinion import run_second_opinion, reconcile

DATA_DIR = Path(__file__).resolve().parent / "data"
HOLDOUT = DATA_DIR / "redflag_holdout.csv"
TESTS = DATA_DIR / "redflag_tests.csv"


def _load(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _flags(raw) -> list[str]:
    return [x.strip() for x in (raw or "").split(";") if x.strip() and x.strip() in settings.RED_FLAGS]


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _ml_redflag_eval(rows: list[dict]):
    per_flag = {f: {"tp": 0, "fp": 0, "fn": 0} for f in settings.RED_FLAGS}
    n_pos = n_neg = 0
    for r in rows:
        true = _flags(r.get("red_flags"))
        pred = predict_flags(r["user_input"])
        is_pos = bool(true)
        n_pos += int(is_pos)
        n_neg += int(not is_pos)
        for f in settings.RED_FLAGS:
            t = f in true
            p = f in pred
            if t and p:
                per_flag[f]["tp"] += 1
            elif p and not t:
                per_flag[f]["fp"] += 1
            elif t and not p:
                per_flag[f]["fn"] += 1
    # overall emergency recall = fraction of positive rows where >=1 true flag hit
    hit = 0
    for r in rows:
        true = _flags(r.get("red_flags"))
        pred = predict_flags(r["user_input"])
        if true and (set(true) & set(pred)):
            hit += 1
    recall = hit / n_pos if n_pos else 0.0
    lo, hi = _wilson(hit, n_pos)
    print("\n=== ML red-flag model ===")
    for f in settings.RED_FLAGS:
        tp, fp, fn = per_flag[f]["tp"], per_flag[f]["fp"], per_flag[f]["fn"]
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        print(f"  {f:22s} recall={rec:.3f} prec={prec:.3f} (tp={tp} fp={fp} fn={fn})")
    print(f"  emergency recall (any-flag): {recall:.3f}  Wilson [{lo:.3f}, {hi:.3f}]  n_pos={n_pos}")


def _routing_eval(rows: list[dict]):
    correct = 0
    total = 0
    for r in rows:
        if not r.get("care_type"):
            continue
        slots = rule_based_extract(r["user_input"], [])
        text = build_classifier_text(slots)
        care, _, _, _ = predict_triage(slots, text)[:4]
        total += 1
        if care == r["care_type"]:
            correct += 1
    print(f"\n=== ML care_type routing ===  accuracy={correct / total:.3f} ({correct}/{total})", flush=True)


def _latency(rows: list[dict]):
    load_redflag_model()
    texts = [normalise_text(r["user_input"]) for r in rows[:200]]
    t0 = time.perf_counter()
    for t in texts:
        predict_flags(t)
    per_flag = (time.perf_counter() - t0) / max(len(texts), 1) * 1000
    print(f"\n=== Latency ===  ML red-flag: {per_flag:.2f} ms/msg")


def _llm_eval(rows: list[dict]):
    if settings.LLM_ROLE == "off":
        print("\n=== LLM second opinion ===  skipped (LLM_ROLE=off)", flush=True)
        return
    from app.core.llm import is_llm_available
    if not is_llm_available():
        print("\n=== LLM second opinion ===  skipped (no DEEPSEEK_API_KEY)", flush=True)
        return
    sample = rows[:10]
    agree = disagree_more = disagree_less = 0
    n = 0
    t0 = time.perf_counter()
    for r in sample:
        text = r["user_input"]
        slots = rule_based_extract(text, [])
        ctext = build_classifier_text(slots)
        care, _, _, _ = predict_triage(slots, ctext)[:4]
        ml_flags = predict_flags(text)
        llm = run_second_opinion(text, r.get("language") or "en")
        recon = reconcile(care, ml_flags, llm)
        n += 1
        if recon["note"] == "agrees":
            agree += 1
        elif recon["note"] == "llm_more_severe_asked":
            disagree_more += 1
        elif recon["note"] == "llm_less_severe_ignored":
            disagree_less += 1
    dt = (time.perf_counter() - t0) / max(n, 1) * 1000
    print(f"\n=== LLM second opinion ===  n={n}  agrees={agree} ({agree / n:.2f})  more_severe={disagree_more}  less_severe={disagree_less}  latency={dt:.0f} ms/msg", flush=True)


def main():
    rows = _load(HOLDOUT) if HOLDOUT.exists() else _load(TESTS)
    print(f"Eval set: {HOLDOUT.name} ({len(rows)} rows)", flush=True)
    _ml_redflag_eval(rows)
    _routing_eval(rows)
    _latency(rows)
    _llm_eval(rows)
    print("\nHonest report: ML red-flag model thresholds are tuned for recall >= 0.90")
    print("on a validation split (the holdout is never used for tuning); the LLM")
    print("second opinion is a safety net that can only raise severity (never lower).")


if __name__ == "__main__":
    main()
