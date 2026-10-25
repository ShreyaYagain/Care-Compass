#!/usr/bin/env python3
"""Run the golden end-to-end scenarios (LLM mocked) and print a pass/fail table.

Reads tests/golden_scenarios.yaml, runs each message through the full pipeline
with the semantic screen mocked (skip or an injected flag list) and the DeepSeek
second opinion disabled, then compares the result against the expected
care_type / urgency / question / red_flag.

Exit code 0 when every scenario passes, 1 otherwise.

Usage:
    python scripts/run_golden.py [--yaml tests/golden_scenarios.yaml]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import yaml

from app.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_YAML = BASE_DIR / "tests" / "golden_scenarios.yaml"


def _run(message: str, lang: str, screen):
    from app.schemas import TriageRequest, Location
    from app.core.pipeline import run_triage_pipeline

    if screen and screen != "skip":
        scr = {"status": "llm_ok", "flags": list(screen), "combined": False}
    else:
        scr = {"status": "skip", "flags": [], "combined": False}
    with patch("app.core.pipeline.screen_red_flags", return_value=scr), \
            patch("app.core.pipeline.run_second_opinion", return_value=None):
        return run_triage_pipeline(
            TriageRequest(user_input=message, language=lang,
                          location=Location(lat=28.54, lng=77.27)),
            debug=True,
        )


def _check(scenario, resp) -> tuple[bool, str]:
    reasons = []
    exp_care = scenario.get("expect_care_type")
    exp_urg = scenario.get("expect_urgency")
    exp_q = scenario.get("expect_question")
    exp_flag = scenario.get("expect_red_flag")
    forbid_emergency = bool(scenario.get("forbid_emergency"))

    if exp_care is not None and resp.care_type != exp_care:
        reasons.append(f"care_type {resp.care_type} != {exp_care}")
    if exp_urg is not None and resp.urgency != exp_urg:
        reasons.append(f"urgency {resp.urgency} != {exp_urg}")
    if exp_q is not None:
        got_q = resp.follow_up_question is not None
        if got_q != bool(exp_q):
            reasons.append(f"question {got_q} != {exp_q}")
    if exp_flag is not None and exp_flag not in (resp.red_flags or []):
        reasons.append(f"red_flag missing {exp_flag}")
    if forbid_emergency and resp.care_type == "emergency_112":
        reasons.append("unexpected emergency_112")
    return (len(reasons) == 0, "; ".join(reasons))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yaml", default=str(DEFAULT_YAML))
    args = parser.parse_args()

    settings.DEEPSEEK_API_KEY = ""

    with open(args.yaml, "r", encoding="utf-8") as f:
        scenarios = yaml.safe_load(f) or []

    print(f"{'message':42s} {'care_type':20s} {'urgency':10s} {'Q':2s} {'red_flag+source':26s} result")
    print("-" * 110)

    n_pass = 0
    n_fail = 0
    for sc in scenarios:
        resp = _run(sc["message"], sc.get("language", "hinglish"), sc.get("screen", "skip"))
        care = resp.care_type or "-"
        urgency = resp.urgency or "-"
        q = "Y" if resp.follow_up_question else "N"
        if sc.get("screen") and sc.get("screen") != "skip":
            source = "semantic_screen"
        elif resp.red_flags:
            source = "rules"
        else:
            source = "-"
        rf = ",".join(resp.red_flags) if resp.red_flags else "-"
        ok, why = _check(sc, resp)
        if ok:
            n_pass += 1
            result = "PASS"
        else:
            n_fail += 1
            result = "FAIL"
        detail = f"{rf}+{source}" if rf != "-" else "-"
        print(f"{sc['message']:42s} {care:20s} {urgency:10s} {q:2s} {detail:26s} {result}")
        if why:
            print(f"{'':42s} {'':20s} {'':10s} {'':2s} {'':26s}   -> {why}")

    print("-" * 110)
    print(f"{n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
