#!/usr/bin/env python3
"""Measure REAL-prompt LLM latency for the DeepSeek reasoning settings.

Uses the actual semantic-screen system prompt + a real message, 20 calls per
setting, and reports p50 / p95 latency and valid-JSON rate for:
  - (deepseek-flash, low effort)
  - (deepseek-flash, default effort = high)
  - (deepseek-v4-pro, low effort)
  - (deepseek-flash, thinking off = reasoning_effort none)   [production choice]

Bypasses the disk cache (calls _chat_completion directly) so latency is real.
No keys are printed.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import warnings
warnings.filterwarnings("ignore")

from app.core.llm import _chat_completion, _parse_json, is_llm_available
from app.core.semantic_screen import SYSTEM_PROMPT, SemanticScreenOut

MSG = "my dad cant breath and his lips are turning blue"
N = 20

CONFIGS = [
    ("flash", "none"),
    ("flash", "low"),
    ("flash", "default"),
    ("pro", "low"),
]


def _model(name: str) -> str:
    return "deepseek-flash" if name == "flash" else "deepseek-v4-pro"


def _measure(model_name: str, effort: str) -> dict:
    lat = []
    valid = 0
    for _ in range(N):
        re_param = None if effort == "default" else effort
        t0 = time.perf_counter()
        content, status = _chat_completion(
            SYSTEM_PROMPT, f"Patient message: \"{MSG}\"",
            model=_model(model_name), timeout=20.0, json_mode=True, temperature=0.0,
            reasoning_effort=re_param, max_tokens=600,
        )
        dt = (time.perf_counter() - t0) * 1000
        lat.append(dt)
        if content:
            data = _parse_json(content)
            try:
                SemanticScreenOut.model_validate(data)
                valid += 1
            except Exception:
                pass
    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(round(0.95 * (len(lat) - 1)))]
    return {"n": N, "p50": p50, "p95": p95, "valid": valid / N}


def main() -> int:
    if not is_llm_available():
        print("No LLM key configured.")
        return 2
    print(f"REAL prompt ({len(SYSTEM_PROMPT)} chars), {N} calls per setting, JSON mode, temp 0, max_tokens 600")
    print(f"{'model':8s} {'effort':8s} {'p50 ms':>9s} {'p95 ms':>9s} {'valid-JSON':>11s}")
    print("-" * 50)
    for model_name, effort in CONFIGS:
        r = _measure(model_name, effort)
        print(f"{model_name:8s} {effort:8s} {r['p50']:9.0f} {r['p95']:9.0f} {r['valid']:>10.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
