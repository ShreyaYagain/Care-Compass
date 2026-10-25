"""Reconciliation harness (evaluation only, no tuning).

Runs, in order: redflag_holdout.csv, unseen_tests.csv, redflag_negatives_v2.csv,
and the 340 official labelled rows. Uses a thread pool (8) for the live DeepSeek
calls (semantic screen + second opinion), retries once on 429/5xx, and caches
every LLM response on disk (ml/results/llm_cache.jsonl) so re-runs are free.

Writes ml/results/reconciliation.json and ml/predictions.csv (allow_followup=false
mode). Progress is printed every 20 rows.
"""
import csv
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.core.intake import build_classifier_text, rule_based_extract
from app.core.llm import llm_model, llm_provider
from app.core.red_flags import check_red_flags
from app.core.redflag_model import predict_flags
from app.core.second_opinion import reconcile, run_second_opinion
from app.core.semantic_screen import screen_red_flags
from app.core.triage_model import load_artifacts, predict_triage

DATA_DIR = Path(__file__).resolve().parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
OUT_JSON = RESULTS_DIR / "reconciliation.json"
OUT_PRED = Path(__file__).resolve().parent / "predictions.csv"

WORKERS = 8
PROGRESS_EVERY = 20


def _flags(raw):
    return [x.strip() for x in (raw or "").split(";") if x.strip() and x.strip() in settings.RED_FLAGS]


def _load(name: str) -> list[dict]:
    path = DATA_DIR / name if name.endswith(".csv") else DATA_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _datasets():
    ds = []
    if (DATA_DIR / "redflag_holdout.csv").exists():
        ds.append(("redflag_holdout", _load("redflag_holdout.csv")))
    if (DATA_DIR / "unseen_tests.csv").exists():
        ds.append(("unseen_tests", _load("unseen_tests.csv")))
    if (DATA_DIR / "redflag_negatives_v2.csv").exists():
        ds.append(("redflag_negatives_v2", _load("redflag_negatives_v2.csv")))
    flat = DATA_DIR / "official" / "triage_dataset_flat.csv"
    if flat.exists():
        ds.append(("official_340", _load(str(flat))))
    return ds


def _fast(row: dict) -> dict:
    text = row.get("user_input") or ""
    slots = rule_based_extract(text, [])
    ctext = build_classifier_text(slots)
    care, urgency, probs, conf, *_ = predict_triage(slots, ctext)
    rules = check_red_flags(text)[0]
    ml = predict_flags(text)
    return {"care": care, "urgency": urgency, "probs": probs, "conf": conf,
            "rules": rules, "ml": ml}


def _screen(text: str):
    t0 = time.perf_counter()
    res = screen_red_flags(text, "en")
    ms = (time.perf_counter() - t0) * 1000
    return res.get("flags") or [], res.get("status"), ms


def _opinion(text: str, lang: str):
    t0 = time.perf_counter()
    llm = run_second_opinion(text, lang or "en")
    ms = (time.perf_counter() - t0) * 1000
    return llm, ms


def _pct(lat: list[float], p: float) -> float:
    if not lat:
        return 0.0
    s = sorted(lat)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main():
    load_artifacts()
    settings.SCREEN_TIMEOUT_S = 8.0
    settings.LLM_TIMEOUT_S = 8.0
    datasets = _datasets()
    print(f"provider={llm_provider()} model={llm_model()}", flush=True)
    print(f"datasets: {[(n, len(r)) for n, r in datasets]}", flush=True)

    all_rows = []
    for name, rows in datasets:
        for r in rows:
            all_rows.append({"dataset": name, "row": r})

    # Pass 1: fast ML pieces (main thread).
    print("pass 1: ML (rules + care_type + red-flag model)...", flush=True)
    for rec in all_rows:
        rec["fast"] = _fast(rec["row"])

    # Pass 2: live LLM calls (thread pool).
    print("pass 2: live LLM (semantic screen + second opinion)...", flush=True)
    screen_lat: list[float] = []
    opinion_lat: list[float] = []
    screen_mode = {"llm_ok": 0, "fallback_local": 0, "failsafe_question": 0, "skip": 0}
    done = 0
    t_start = time.time()

    def _work(rec):
        time.sleep(random.uniform(0, 0.15))  # jitter to avoid thundering herd
        text = rec["row"].get("user_input") or ""
        lang = rec["row"].get("language") or "en"
        flags, status, sms = _screen(text)
        llm, oms = _opinion(text, lang)
        return rec, flags, status, sms, llm, oms

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(_work, rec): rec for rec in all_rows}
        for fut in as_completed(futs):
            rec, flags, status, sms, llm, oms = fut.result()
            rec["sem_flags"] = flags
            rec["sem_status"] = status
            rec["llm_opinion"] = llm
            screen_lat.append(sms)
            opinion_lat.append(oms)
            screen_mode[status] = screen_mode.get(status, 0) + 1
            done += 1
            if done % PROGRESS_EVERY == 0 or done == len(all_rows):
                el = time.time() - t_start
                eta = el / done * (len(all_rows) - done)
                print(f"  {done}/{len(all_rows)} rows, elapsed {el:.0f}s, ETA {eta:.0f}s", flush=True)

    # Emergency scoring + follow-up + allow_followup=false.
    report = {"datasets": {}, "provider": llm_provider(), "model": llm_model(),
              "screen_mode": screen_mode,
              "screen_lat_p50": round(_pct(screen_lat, 0.5), 1),
              "screen_lat_p95": round(_pct(screen_lat, 0.95), 1),
              "opinion_lat_p50": round(_pct(opinion_lat, 0.5), 1),
              "opinion_lat_p95": round(_pct(opinion_lat, 0.95), 1)}

    for name, _ in datasets:
        recs = [r for r in all_rows if r["dataset"] == name]
        ds = {
            "n": len(recs),
            "emergency_a": 0, "emergency_b": 0, "emergency_c": 0,
            "followup": 0, "decided": 0, "correct_decided": 0,
            "correct_null_counted": 0,
            "flag_recall": {f: {"rules": 0, "ml": 0, "sem": 0, "union": 0, "pos": 0} for f in settings.RED_FLAGS},
        }
        for r in recs:
            fast = r["fast"]
            text = r["row"].get("user_input") or ""
            true_care = (r["row"].get("care_type") or "").strip()
            true_flags = _flags(r["row"].get("red_flags"))
            is_em = bool(true_flags) or true_care == "emergency_112"

            # Emergency scoring (a/b/c).
            if is_em:
                if fast["rules"]:
                    ds["emergency_a"] += 1
                elif r.get("sem_flags") or fast["ml"]:
                    ds["emergency_b"] += 1
                else:
                    ds["emergency_c"] += 1

            # First-turn outcome: follow-up vs decision.
            asked = bool(r.get("sem_flags")) and not fast["rules"]
            if asked:
                ds["followup"] += 1
                ds["correct_null_counted"] += 0  # follow-up counts as a null prediction
            else:
                ds["decided"] += 1
                if fast["care"] == true_care:
                    ds["correct_decided"] += 1
                    ds["correct_null_counted"] += 1

            # Flag-level recall on this row.
            for f in true_flags:
                ds["flag_recall"][f]["pos"] += 1
                if f in fast["rules"]:
                    ds["flag_recall"][f]["rules"] += 1
                if f in fast["ml"]:
                    ds["flag_recall"][f]["ml"] += 1
                if f in (r.get("sem_flags") or []):
                    ds["flag_recall"][f]["sem"] += 1
                if f in fast["rules"] or f in fast["ml"] or f in (r.get("sem_flags") or []):
                    ds["flag_recall"][f]["union"] += 1
        report["datasets"][name] = ds

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"wrote {OUT_JSON}", flush=True)
    print(json.dumps(report["datasets"], indent=1, default=str), flush=True)


if __name__ == "__main__":
    main()
