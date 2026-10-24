"""TASK B2 — MMCQS robustness run through the /triage pipeline.

Runs a sample of MMCQS code-mixed queries through the triage pipeline (Groq on
and off) and reports:
  % decided, % follow-up, % defaulted to teleconsultation, % flagged emergency,
  median latency, crash count (must be 0).

Prints 10 examples of each outcome. Outputs the table to docs/ROBUSTNESS_REPORT.md.
"""
from __future__ import annotations

import csv
import json
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.schemas import TriageRequest
from app.core.pipeline import run_triage_pipeline
from app.core.llm import is_groq_available

RAW_DIR = Path(__file__).resolve().parent / "raw"
DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
REPORT_FILE = DOCS_DIR / "ROBUSTNESS_REPORT.md"

DEFAULT_OFF_N = 500
DEFAULT_ON_N = 30


def _load_queries(n: int) -> list[str]:
    path = RAW_DIR / "mmcqs_hf.jsonl"
    queries = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    queries.append(json.loads(line).get("Codemixed_Question", ""))
    if not queries:
        sample = RAW_DIR / "mmcqs_sample.csv"
        if sample.exists():
            with open(sample, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    queries.append(row.get("Codemixed_Question", ""))
    queries = [q for q in queries if q and q.strip()]
    return queries[:n]


def _run(q: str) -> dict:
    req = TriageRequest(user_input=q, language="hinglish", conversation_history=[])
    t0 = time.time()
    resp = run_triage_pipeline(req)
    return {
        "care_type": resp.care_type,
        "urgency": resp.urgency,
        "follow_up": resp.follow_up_question,
        "red_flags": resp.red_flags,
        "latency_ms": (time.time() - t0) * 1000,
    }


def run_robustness(n_off: int, n_on: int, groq_enabled: bool) -> dict:
    queries_off = _load_queries(n_off)
    results_off = []
    crashes = 0
    for q in queries_off:
        try:
            results_off.append(_run(q))
        except Exception as e:
            crashes += 1

    results_on = []
    if groq_enabled and is_groq_available():
        for q in _load_queries(n_on):
            try:
                results_on.append(_run(q))
            except Exception:
                crashes += 1

    return {
        "off": results_off,
        "on": results_on,
        "crashes": crashes,
        "n_off": len(queries_off),
        "n_on": len(results_on),
    }


def _summarize(results: list[dict]) -> dict:
    if not results:
        return {"n": 0, "decided": 0, "follow_up": 0, "default_teleconsult": 0,
                "flagged_emergency": 0, "median_latency_ms": 0.0, "emergency_list": [],
                "examples": {"decided": [], "follow_up": [], "default_teleconsult": [], "emergency": []}}
    n = len(results)
    decided = [r for r in results if r["care_type"] is not None]
    follow_up = [r for r in results if r["care_type"] is None]
    emergency = [r for r in results if r["care_type"] == "emergency_112"]
    # "defaulted to teleconsultation" = decided teleconsultation where red_flags empty
    default_tc = [r for r in decided if r["care_type"] == "teleconsultation" and not r["red_flags"]]

    examples = {
        "decided": decided[:10],
        "follow_up": follow_up[:10],
        "default_teleconsult": default_tc[:10],
        "emergency": emergency[:10],
    }
    return {
        "n": n,
        "decided": len(decided),
        "follow_up": len(follow_up),
        "default_teleconsult": len(default_tc),
        "flagged_emergency": len(emergency),
        "median_latency_ms": statistics.median([r["latency_ms"] for r in results]),
        "emergency_list": [r for r in emergency],
        "examples": examples,
    }


def _pct(num: int, den: int) -> str:
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", type=int, default=DEFAULT_OFF_N)
    ap.add_argument("--on", type=int, default=DEFAULT_ON_N)
    ap.add_argument("--groq", action="store_true", help="also run the Groq-on sample")
    args = ap.parse_args()

    result = run_robustness(args.off, args.on, args.groq)

    lines = ["# MMCQS Robustness Report", "",
             "Robustness of the CareCompass pipeline on code-mixed Hinglish queries",
             "(MMCQS / MedSumm, `ArkaAcharya/MMCQSD`, CC-BY-4.0).", ""]

    for mode, res in (("Groq OFF", result["off"]), ("Groq ON", result["on"])):
        s = _summarize(res)
        print(f"\n===== {mode} (n={s['n']}) =====")
        print(f"  decided: {s['decided']} ({_pct(s['decided'], s['n'])})")
        print(f"  follow-up: {s['follow_up']} ({_pct(s['follow_up'], s['n'])})")
        print(f"  default teleconsultation: {s['default_teleconsult']} ({_pct(s['default_teleconsult'], s['n'])})")
        print(f"  flagged emergency: {s['flagged_emergency']} ({_pct(s['flagged_emergency'], s['n'])})")
        print(f"  median latency: {s['median_latency_ms']:.1f} ms")
        print(f"  crashes: {result['crashes']}")

        lines += [f"## {mode} (n={s['n']})", "",
                  f"| Metric | Value |", "|---|---|",
                  f"| Decided | {_pct(s['decided'], s['n'])} |",
                  f"| Follow-up | {_pct(s['follow_up'], s['n'])} |",
                  f"| Defaulted to teleconsultation | {_pct(s['default_teleconsult'], s['n'])} |",
                  f"| Flagged emergency | {_pct(s['flagged_emergency'], s['n'])} |",
                  f"| Median latency (ms) | {s['median_latency_ms']:.1f} |",
                  f"| Crashes | {result['crashes']} (must be 0) |", ""]

        for label in ("decided", "follow_up", "default_teleconsult", "emergency"):
            print(f"\n  --- 10 example {label} ---")
            for r in s["examples"][label][:10]:
                print(f"    - {r['care_type'] or 'follow_up'} / {r['urgency']}")

    lines += ["", "## Emergency-flagged queries (for manual check)", ""]
    if result["off"]:
        em = [r for r in result["off"] if r["care_type"] == "emergency_112"]
        if em:
            for r in em[:20]:
                lines.append(f"- {r['care_type']} / {r['urgency']} flags={r['red_flags']}")
        else:
            lines.append("- (none)")
    lines.append("")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {REPORT_FILE}")


if __name__ == "__main__":
    main()
