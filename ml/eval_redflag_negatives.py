"""One-shot evaluation of the semantic red-flag screen on 60 hard
non-emergency cases (ml/data/redflag_negatives_v2.csv).

The screen is run EXACTLY once per text with NO tuning; a row counts as a
false alarm when the screen would ask any question (flags non-empty) or
trigger the combined failsafe question. Reports overall + per-category false
alarm rates with Wilson 95% intervals, plus the screen-status histogram
(groq_ok vs failsafe due to rate limits).

Usage:
    .venv/bin/python ml/eval_redflag_negatives.py [--pace 8.0]
"""
import argparse
import csv
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.semantic_screen import screen_red_flags, _SCREEN_CACHE  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "redflag_negatives_v2.csv"


def wilson(p: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pace", type=float, default=0.0,
                    help="sleep between screen calls to stay under the Groq TPM limit")
    ap.add_argument("--workers", type=int, default=4,
                    help="concurrent screen calls (kept low to respect the TPM limit)")
    args = ap.parse_args()

    with open(DATA, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} hard non-emergency cases (redflag_negatives_v2.csv)")

    def _screen(row):
        text = row["user_input"]
        _SCREEN_CACHE.pop(text, None)
        res = screen_red_flags(text)
        if args.pace:
            time.sleep(args.pace)
        return {
            "text": text,
            "category": row["category"],
            "false_alarm": bool(res.get("flags")) or bool(res.get("combined")),
            "status": res.get("status"),
            "flags": res.get("flags") or [],
        }

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_screen, rows))

    statuses = Counter(r["status"] for r in results)

    n = len(results)
    fa = sum(1 for r in results if r["false_alarm"])
    rate = fa / n if n else 0.0
    lo, hi = wilson(rate, n)
    print(f"\n=== SCREEN ONCE, NO TUNING ({n} rows) ===")
    print(f"screen status histogram: {dict(statuses)}")
    print(f"FALSE ALARMS: {fa}/{n} -> rate={rate:.3f} (Wilson 95% [{lo:.3f}, {hi:.3f}])")

    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    print("\nPer category:")
    for cat in sorted(by_cat):
        rows_c = by_cat[cat]
        fa_c = sum(1 for r in rows_c if r["false_alarm"])
        rc = fa_c / len(rows_c)
        lo_c, hi_c = wilson(rc, len(rows_c))
        print(f"  {cat:20s} n={len(rows_c):2d} false_alarms={fa_c:2d} "
              f"rate={rc:.3f} (Wilson [{lo_c:.3f}, {hi_c:.3f}])")

    print("\nFalse-alarm details:")
    for r in results:
        if r["false_alarm"]:
            print(f"  [{r['category']}] {r['text']!r} -> status={r['status']} flags={r['flags']}")


if __name__ == "__main__":
    main()
