#!/usr/bin/env python3
"""Part 5 gate: one-shot policy's false-alarm rate on the hard negatives.

Runs the FULL one-shot pipeline (allow_followup=false, live DeepSeek semantic
screen) over the hard non-emergency rows:
  - ml/data/redflag_negatives_v2.csv (60 rows)
  - ml/data/redflag_tests.csv non-emergency rows (80 negated/near-miss rows)

A row is a FALSE ALARM when the one-shot policy escalates it to emergency_112.
If the false-alarm rate exceeds 5%, the script stops and prints the offending
examples (no further evaluation is meaningful). Uses 3 workers, resumes from the
disk LLM cache, and aborts after 3 consecutive provider failures.

Usage: .venv/bin/python ml/eval_hard_negatives_gate.py
"""
from __future__ import annotations

import csv
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas import Location, TriageRequest
from app.core.llm import consecutive_llm_failures
from app.core.pipeline import run_triage_pipeline

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results" / "hard_negatives_gate.json"
LOC = Location(lat=28.54, lng=77.27)
MAX_FALSE_ALARM_RATE = 0.05
WORKERS = 3
CALL_DELAY_S = 1.0
TIMEOUT_S = 8.0
STOP_AFTER_FAILURES = 3


def _wilson(p: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _load_negatives() -> list[dict]:
    rows = []
    with open(DATA / "redflag_negatives_v2.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"text": r["user_input"], "category": "negatives_v2",
                         "subcategory": r.get("category", ""), "lang": "hinglish"})
    with open(DATA / "redflag_tests.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["care_type"] != "emergency_112":
                rows.append({"text": r["user_input"], "category": "near_miss",
                             "subcategory": "", "lang": r.get("language", "en")})
    return rows


def _run(row: dict) -> dict:
    from unittest.mock import patch
    # Pace requests to respect the provider's rate limit.
    time.sleep(CALL_DELAY_S)
    # The second opinion can only agree/raise (never lower) and cannot change
    # care_type in one-shot mode, so it is skipped here; the one-shot escalation
    # is driven solely by the semantic screen flags.
    with patch("app.core.pipeline.run_second_opinion", return_value=None):
        resp = run_triage_pipeline(
            TriageRequest(user_input=row["text"], language=row["lang"], location=LOC,
                          allow_followup=False, context_consent=False),
            debug=False,
        )
    return {"text": row["text"], "category": row["category"],
            "care_type": resp.care_type, "flags": resp.red_flags or []}


def main() -> int:
    rows = _load_negatives()
    n_v2 = sum(1 for r in rows if r["category"] == "negatives_v2")
    n_nm = sum(1 for r in rows if r["category"] == "near_miss")
    print(f"Hard negatives: {n_v2} (redflag_negatives_v2) + {n_nm} (negated/near-miss) = {len(rows)}")

    # 8s timeout for the live screen/mapper calls, thinking off (fast model).
    from app.config import settings
    settings.SCREEN_TIMEOUT_S = TIMEOUT_S
    settings.LLM_TIMEOUT_S = TIMEOUT_S
    from app.core.llm import llm_fast_model, llm_fast_effort
    print(f"LLM: {llm_fast_model()} effort={llm_fast_effort()} timeout={TIMEOUT_S}s workers={WORKERS} delay={CALL_DELAY_S}s")

    # Pre-load the embedding model single-threaded (torch + a thread pool can
    # segfault on concurrent model load); the one-shot gate does not depend on it.
    from app.core.open_vocab import embedding_match
    embedding_match("prewarm")

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(_run, r): r for r in rows}
        for fut in as_completed(futs):
            results.append(fut.result())
            if consecutive_llm_failures() >= STOP_AFTER_FAILURES:
                print(f"STOPPED: {STOP_AFTER_FAILURES} consecutive provider failures.")
                return 2

    false_alarms = [r for r in results if r["care_type"] == "emergency_112"]
    n = len(results)
    fa = len(false_alarms)
    rate = fa / n if n else 0.0
    lo, hi = _wilson(rate, n)
    print(f"\nOne-shot false-alarm rate: {fa}/{n} = {rate:.4f} (Wilson 95% [{lo:.4f}, {hi:.4f}])")

    by_cat = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)
    for cat in ("negatives_v2", "near_miss"):
        if cat in by_cat:
            rows_c = by_cat[cat]
            fa_c = sum(1 for r in rows_c if r["care_type"] == "emergency_112")
            print(f"  {cat:14s} n={len(rows_c):3d} false_alarms={fa_c} "
                  f"rate={fa_c / len(rows_c):.4f}")

    examples = [{"category": r["category"], "text": r["text"], "flags": r["flags"]}
                for r in false_alarms]
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(__import__("json").dumps(
        {"n": n, "false_alarms": fa, "rate": rate, "wilson": [lo, hi],
         "by_category": {c: len(v) for c, v in by_cat.items()},
         "examples": examples}, indent=2), encoding="utf-8")
    print(f"Saved {RESULTS}")

    if rate > MAX_FALSE_ALARM_RATE:
        print(f"\nFALSE-ALARM RATE {rate:.4f} EXCEEDS {MAX_FALSE_ALARM_RATE:.2f} — STOPPING.")
        print("Examples:")
        for r in false_alarms:
            print(f"  [{r['category']}] {r['text']!r} -> flags={r['flags']}")
        return 1

    print(f"\nGate passed (false-alarm rate {rate:.4f} <= {MAX_FALSE_ALARM_RATE:.2f}).")
    if false_alarms:
        print("False-alarm examples (for the record):")
        for r in false_alarms:
            print(f"  [{r['category']}] {r['text']!r} -> flags={r['flags']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
