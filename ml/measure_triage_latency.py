"""End-to-end /triage latency measurement (screen ON, against Groq).

Runs the ASYNC triage path (run_triage_pipeline_async — the same code the
/triage endpoint uses, where the semantic screen and intake extraction run in
parallel via asyncio.gather) over a fixed message set and reports p50/p95.

Usage:
    .venv/bin/python ml/measure_triage_latency.py            # parallel (async) path
    .venv/bin/python ml/measure_triage_latency.py --sync     # legacy sequential path
    .venv/bin/python ml/measure_triage_latency.py --runs 3
"""
import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas import TriageRequest, Location  # noqa: E402
from app.core.pipeline import run_triage_pipeline, run_triage_pipeline_async  # noqa: E402
from app.core.semantic_screen import _SCREEN_CACHE  # noqa: E402

LOC = Location(lat=28.54, lng=77.27)

MESSAGES = [
    "my dad feels weird and sweaty today",
    "mummy ko kal se pet mein dard hai",
    "baby ko halka bukhar hai aur ro raha hai",
    "ghutne mein dard ho raha hai chadhte utarte waqt",
    "sir mein dard hai aur thoda chakkar aa raha hai",
    "grandmother is feeling weak since two days",
    "skin par dane ho gaye hain aur khujli hai",
    "paer mein moch aa gayi hai football khelte time",
    "koi injection lagane ke liye nurse chahiye",
    "blood test karwana hai ghar par",
]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(p * len(ordered)))
    return ordered[idx]


async def run_async(runs: int, pace: float) -> list[float]:
    lat = []
    for run in range(runs):
        for m in MESSAGES:
            key = f"{run}:{m}"
            _SCREEN_CACHE.pop(m, None)
            req = TriageRequest(user_input=m, language="auto", location=LOC, conversation_history=[])
            t0 = time.perf_counter()
            await run_triage_pipeline_async(req)
            lat.append(time.perf_counter() - t0)
            time.sleep(pace)
    return lat


def run_sync(runs: int, pace: float) -> list[float]:
    lat = []
    for run in range(runs):
        for m in MESSAGES:
            _SCREEN_CACHE.pop(m, None)
            req = TriageRequest(user_input=m, language="auto", location=LOC, conversation_history=[])
            t0 = time.perf_counter()
            run_triage_pipeline(req)
            lat.append(time.perf_counter() - t0)
            time.sleep(pace)
    return lat


def report(label: str, lat: list[float]) -> None:
    p50 = percentile(lat, 0.50)
    p95 = percentile(lat, 0.95)
    print(f"\n{label}: n={len(lat)} "
          f"p50={p50:.3f}s p95={p95:.3f}s "
          f"mean={statistics.mean(lat):.3f}s max={max(lat):.3f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--pace", type=float, default=1.0,
                    help="sleep between messages (stay under the Groq TPM limit)")
    ap.add_argument("--sync", action="store_true", help="sequential (legacy) path")
    args = ap.parse_args()

    if args.sync:
        report("SYNC pipeline (sequential screen+intake)", run_sync(args.runs, args.pace))
    else:
        report("ASYNC pipeline (screen || intake via asyncio.gather)", asyncio.run(run_async(args.runs, args.pace)))


if __name__ == "__main__":
    main()
