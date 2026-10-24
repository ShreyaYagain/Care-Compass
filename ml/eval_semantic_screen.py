"""Evaluate the semantic red-flag screen on ml/data/redflag_holdout.csv.

Reports, per mode (rules only / semantic screen only / full pipeline):
  - safety recall (immediate emergency + confirmation asked)
  - false-alarm rate on the non-emergency rows
  - confirmation vs immediate-decision counts
  - Wilson 95% intervals

The holdout is NEVER used for tuning — thresholds were fixed in
ml/train_semantic_fallback.py on the 217-row set. Run with Groq enabled for the
real semantic screen (falls back to the local classifier otherwise).
"""
import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.language import normalise_text
from app.core.red_flags import check_red_flags
from app.core.semantic_screen import screen_red_flags
from app.core.llm import is_groq_available
from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline

HOLDOUT = Path(__file__).resolve().parent / "data" / "redflag_holdout.csv"
LOC = Location(lat=28.54, lng=77.27)

RED_FLAG_SCREEN_IDS = {
    "breathing_difficulty", "chest_pain_check", "consciousness_check",
    "bleeding_check", "infant_fever_age_check", "dehydration_check",
    "stroke_check", "seizure_check", "suicidal_check",
}


def wilson(p: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def load():
    with open(HOLDOUT, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    pos = [r for r in rows if r["care_type"] == "emergency_112"]
    neg = [r for r in rows if r["care_type"] != "emergency_112"]
    return pos, neg


def rules_only(text: str) -> bool:
    _, _, _, is_em = check_red_flags(text, normalise_text(text), return_medium=True)
    return bool(is_em)


def semantic_only(text: str) -> bool:
    res = screen_red_flags(text)
    return bool(res.get("flags")) or bool(res.get("combined"))


def pipeline_outcome(rules_em: bool, screen_flags: list[str]) -> str:
    """Simulates the pipeline's safety outcome (emergency -> confirmation -> missed).
    The real pipeline is covered by tests/test_semantic_screen.py; the intake
    LLM call is irrelevant to the safety outcome, so it is skipped here."""
    if rules_em:
        return "emergency"
    if screen_flags:
        return "confirmation"
    return "missed"


def report_mode(name: str, pos_results: list[str], neg_results: list[str]) -> None:
    n_pos = len(pos_results)
    n_neg = len(neg_results)
    caught = sum(1 for r in pos_results if r in ("emergency", "confirmation"))
    immediate = sum(1 for r in pos_results if r == "emergency")
    confirmed = sum(1 for r in pos_results if r == "confirmation")
    missed = n_pos - caught
    fa = sum(1 for r in neg_results if r in ("emergency", "confirmation"))
    rec = caught / n_pos if n_pos else 0.0
    lo, hi = wilson(rec, n_pos)
    print(f"\n=== {name} ===")
    print(f"  positives n={n_pos}: immediate emergency={immediate}, confirmation={confirmed}, "
          f"missed={missed} -> safety recall={rec:.3f} (Wilson [{lo:.3f}, {hi:.3f}])")
    fa_rate = fa / n_neg if n_neg else 0.0
    fa_lo, fa_hi = wilson(fa_rate, n_neg)
    print(f"  negatives n={n_neg}: false alarms={fa} -> rate={fa_rate:.3f} (Wilson [{fa_lo:.3f}, {fa_hi:.3f}])")


def main():
    import time
    pos, neg = load()
    print(f"Holdout: {len(pos)} positives, {len(neg)} non-emergency. "
          f"Groq screen: {'ENABLED' if is_groq_available() else 'FALLBACK (local TF-IDF)'}")

    pos_rules = ["emergency" if rules_only(r["user_input"]) else "missed" for r in pos]
    neg_rules = ["emergency" if rules_only(r["user_input"]) else "ok" for r in neg]
    report_mode("RULES ONLY (keyword rules)", pos_rules, neg_rules)

    # Screen each unique text once (memoized), paced to respect the Groq TPM limit.
    screen_flags_by_text = {}
    for r in pos + neg:
        t = r["user_input"]
        if t not in screen_flags_by_text:
            screen_flags_by_text[t] = screen_red_flags(t)
            time.sleep(0.5)

    pos_sem = ["confirmation" if (screen_flags_by_text[r["user_input"]].get("flags") or screen_flags_by_text[r["user_input"]].get("combined")) else "missed" for r in pos]
    neg_sem = ["confirmation" if (screen_flags_by_text[r["user_input"]].get("flags") or screen_flags_by_text[r["user_input"]].get("combined")) else "ok" for r in neg]
    report_mode("SEMANTIC SCREEN ONLY (confirm-or-skip)", pos_sem, neg_sem)

    def _screen_signal(t: str) -> list[str]:
        res = screen_flags_by_text.get(t, {})
        return list(res.get("flags") or []) + (["combined"] if res.get("combined") else [])

    pos_full = [pipeline_outcome(rules_only(r["user_input"]), _screen_signal(r["user_input"])) for r in pos]
    neg_full = [pipeline_outcome(rules_only(r["user_input"]), _screen_signal(r["user_input"])) for r in neg]
    report_mode("FULL PIPELINE (rules + semantic + classifier)", pos_full, neg_full)

    missed = [(r["user_input"], _screen_signal(r["user_input"])) for r in pos
              if pipeline_outcome(rules_only(r["user_input"]), _screen_signal(r["user_input"])) == "missed"]
    print(f"\nFull-pipeline missed positives ({len(missed)}):")
    for text, flags in missed:
        print(f"  - {text!r} (screen flags={flags})")


if __name__ == "__main__":
    main()
