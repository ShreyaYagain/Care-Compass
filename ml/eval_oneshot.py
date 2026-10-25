"""One-shot (allow_followup=false) evaluation + predictions.csv + negatives
false alarms, reusing the disk LLM cache."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas import Location, TriageRequest
from app.core.pipeline import run_triage_pipeline

DATA_DIR = Path(__file__).resolve().parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
LOC = Location(lat=28.54, lng=77.27)


def _load(p):
    with open(p, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _run(text, lang):
    return run_triage_pipeline(
        TriageRequest(user_input=text, language=lang or "en", location=LOC,
                      allow_followup=False, context_consent=False),
    )


def main():
    # 1. holdout + unseen: emergency recall in one-shot mode.
    rows = []
    for name in ("redflag_holdout.csv", "unseen_tests.csv"):
        for r in _load(DATA_DIR / name):
            r["_ds"] = name
            rows.append(r)

    correct = n = 0
    em_caught = em_total = 0
    pred_rows = []
    for r in rows:
        resp = _run(r["user_input"], r.get("language") or "en")
        care = resp.care_type or "teleconsultation"
        urg = resp.urgency or "same_day"
        flags = resp.red_flags or []
        if flags:
            care, urg = "emergency_112", "emergency"
        pred_rows.append([r["id"], care, urg, ";".join(sorted(set(flags)))])
        tc = (r.get("care_type") or "").strip()
        if tc:
            n += 1
            if care == tc:
                correct += 1
            if tc == "emergency_112":
                em_total += 1
                if care == "emergency_112":
                    em_caught += 1

    with open(Path(__file__).resolve().parent / "predictions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "care_type", "urgency", "red_flags"])
        w.writerows(pred_rows)

    print(f"ONE-SHOT (allow_followup=false) holdout+unseen n={n}")
    print(f"  accuracy: {correct / n:.4f} ({correct}/{n})")
    print(f"  emergency recall: {em_caught / em_total if em_total else 0:.4f} ({em_caught}/{em_total})")
    print(f"  predictions.csv rows: {len(pred_rows)}")

    # 2. false alarms on redflag_negatives_v2.csv (all expected non-emergency).
    negs = _load(DATA_DIR / "redflag_negatives_v2.csv")
    fa = 0
    fa_rows = []
    for r in negs:
        resp = _run(r["user_input"], "hinglish")
        if resp.care_type == "emergency_112" or (resp.red_flags or []):
            fa += 1
            fa_rows.append((r["user_input"], resp.red_flags))
    print(f"\nFALSE ALARMS on redflag_negatives_v2.csv (n={len(negs)}): {fa}")
    for t, f in fa_rows:
        print(f"  - {t!r} -> {f}")


if __name__ == "__main__":
    main()
