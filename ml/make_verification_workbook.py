"""MODEL VERIFICATION WORKBOOK.

Evaluates ONLY what is in production (no retraining, no tuning). Writes:

  - ml/results/verification.xlsx      (openpyxl; frozen header, filters, red
                                       rows for wrong predictions)
  - ml/results/verification_<sheet>.csv  (one CSV per sheet)
  - ml/predictions.csv                (official hackathon format)

Sheets: Summary, Predictions, Confusion, Errors, RedFlags, Features, Provenance,
SecondOpinion.

The Summary sheet also carries the OVERRIDE AUDIT (ml/audit_overrides.py):
the override rate of the full deterministic pipeline (final care_type vs raw
ML argmax) per dataset plus per-stage override counts. No thresholds tuned.

Evaluated on: official train/val (marked leaky), redflag_holdout.csv,
unseen_tests.csv, and human_holdout.csv when present (skipped with a note when
missing). The exact-text grouped-CV figure is read from
ml/results/comparison.json (recorded at model selection time; the production
model is not re-fit here).
"""
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.config import settings
from app.core.intake import build_classifier_text, rule_based_extract
from app.core.red_flags import check_red_flags
from app.core.redflag_model import predict_flags
from app.core.semantic_screen import _local_screen
from app.core.triage_model import load_artifacts, predict_triage

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "ml" / "data"
RESULTS_DIR = ROOT / "ml" / "results"
RESULTS_DIR.mkdir(exist_ok=True)

XLSX = RESULTS_DIR / "verification.xlsx"
PREDICTIONS_CSV = ROOT / "ml" / "predictions.csv"
COMPARISON_JSON = RESULTS_DIR / "comparison.json"

CARE_TYPES = settings.CARE_TYPES
RED_FLAGS = settings.RED_FLAGS

_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_WRONG_FILL = PatternFill("solid", fgColor="FFC7CE")
_NOTE_FILL = PatternFill("solid", fgColor="FFF2CC")


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _load_csv(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

def _datasets() -> list[dict]:
    ds = [
        {"name": "official_train", "path": DATA_DIR / "train.csv", "use": "train",
         "human_reviewed": "no", "leaky": True, "source": "official_sanocare"},
        {"name": "official_val", "path": DATA_DIR / "val.csv", "use": "validation",
         "human_reviewed": "no", "leaky": True, "source": "official_sanocare"},
        {"name": "redflag_holdout", "path": DATA_DIR / "redflag_holdout.csv", "use": "test",
         "human_reviewed": "no", "leaky": False, "source": "ai_drafted_holdout"},
        {"name": "unseen_tests", "path": DATA_DIR / "unseen_tests.csv", "use": "test",
         "human_reviewed": "no", "leaky": False, "source": "ai_drafted_unseen"},
    ]
    human = DATA_DIR / "human_holdout.csv"
    if human.exists():
        ds.append({"name": "human_holdout", "path": human, "use": "test",
                   "human_reviewed": "yes", "leaky": False, "source": "human_holdout"})
    return ds


def _true_flags(row: dict) -> list[str]:
    raw = row.get("red_flags") or ""
    return [x.strip() for x in raw.split(";") if x.strip() and x.strip() in RED_FLAGS]


def _predict(text: str) -> dict:
    slots = rule_based_extract(text, [])
    ctext = build_classifier_text(slots)
    care, urgency, probs, conf, top_terms, _ = predict_triage(slots, ctext)
    rules_flags = check_red_flags(text)[0]
    ml_flags = predict_flags(text)
    sem_flags = _local_screen(text)
    # Deterministic safety rules run first in production and can only raise:
    # any high red flag routes to emergency_112, overriding the ML classifier.
    if rules_flags:
        care = "emergency_112"
        urgency = "emergency"
    return {
        "care": care, "urgency": urgency, "probs": probs, "conf": conf,
        "top_terms": top_terms, "rules": rules_flags, "ml": ml_flags, "sem": sem_flags,
    }


# ---------------------------------------------------------------------------
# Evaluation records
# ---------------------------------------------------------------------------

def _evaluate():
    load_artifacts()
    datasets = _datasets()
    predictions: list[dict] = []
    per_dataset: dict[str, list[dict]] = defaultdict(list)

    for ds in datasets:
        for row in _load_csv(ds["path"]):
            text = row.get("norm_input") or row.get("user_input") or ""
            true_care = (row.get("care_type") or "").strip()
            pred = _predict(text)
            rec = {
                "id": row.get("id", ""),
                "text": text,
                "language": row.get("language", ""),
                "true_care_type": true_care,
                "predicted_care_type": pred["care"],
                "probs": pred["probs"],
                "correct": (pred["care"] == true_care) if true_care else None,
                "source_dataset": ds["name"],
                "dataset_leaky": ds["leaky"],
                "true_flags": _true_flags(row),
                "rules_flags": pred["rules"],
                "ml_flags": pred["ml"],
                "sem_flags": pred["sem"],
                "top_terms": pred["top_terms"],
            }
            predictions.append(rec)
            per_dataset[ds["name"]].append(rec)

    return datasets, predictions, per_dataset


def _macro_f1(records: list[dict]) -> float:
    tp_fp_fn = {c: [0, 0, 0] for c in CARE_TYPES}  # tp, fp, fn
    for r in records:
        if not r["true_care_type"]:
            continue
        t, p = r["true_care_type"], r["predicted_care_type"]
        if t not in CARE_TYPES:
            continue
        for c in CARE_TYPES:
            if c == t and c == p:
                tp_fp_fn[c][0] += 1
            elif c == p:
                tp_fp_fn[c][1] += 1
            elif c == t:
                tp_fp_fn[c][2] += 1
    f1s = []
    for c in CARE_TYPES:
        tp, fp, fn = tp_fp_fn[c]
        f1s.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)
    return sum(f1s) / len(f1s)


def _emergency_stats(records: list[dict]) -> dict:
    tp = fp = fn = 0
    for r in records:
        if not r["true_care_type"]:
            continue
        t_em = r["true_care_type"] == "emergency_112"
        p_em = r["predicted_care_type"] == "emergency_112"
        if t_em and p_em:
            tp += 1
        elif p_em and not t_em:
            fp += 1
        elif t_em and not p_em:
            fn += 1
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "recall": recall, "n_pos": tp + fn}


def _flag_detection_recall(records: list[dict]) -> tuple[int, int]:
    """Of rows carrying a true red flag, how many have >=1 flag caught by the
    rules, the ML red-flag model or the semantic screen (the safety net)."""
    n = caught = 0
    for r in records:
        if not r["true_flags"]:
            continue
        n += 1
        any_method = set(r["rules_flags"]) | set(r["ml_flags"]) | set(r["sem_flags"])
        if any(flag in any_method for flag in r["true_flags"]):
            caught += 1
    return caught, n


def _build_confusion(records: list[dict]) -> tuple[list[list[int]], list[list[float]]]:
    idx = {c: i for i, c in enumerate(CARE_TYPES)}
    counts = [[0] * len(CARE_TYPES) for _ in range(len(CARE_TYPES))]
    for r in records:
        t, p = r["true_care_type"], r["predicted_care_type"]
        if t in idx and p in idx:
            counts[idx[t]][idx[p]] += 1
    norm = []
    for row in counts:
        s = sum(row)
        norm.append([round(x / s, 3) if s else 0.0 for x in row])
    return counts, norm


# ---------------------------------------------------------------------------
# Features: top 15 words per care type (aggregated to whole words)
# ---------------------------------------------------------------------------

def _top_words_per_care_type() -> dict[str, list[str]]:
    import joblib
    from app.core.language import normalise_text
    from ml.explain_model import _canonicalise

    vec = joblib.load(settings.ARTIFACTS_DIR / "tfidf_vectorizer.joblib")
    clf = joblib.load(settings.ARTIFACTS_DIR / "triage_care.joblib")
    if hasattr(clf, "calibrated_classifiers_"):
        est = clf.calibrated_classifiers_[0].estimator
    elif hasattr(clf, "estimator") and hasattr(clf.estimator, "coef_"):
        est = clf.estimator
    else:
        est = clf
    classes = list(clf.classes_)
    feature_names = list(vec.get_feature_names_out())
    coefs = est.coef_

    out: dict[str, list[str]] = {}
    for ci, cls in enumerate(classes):
        if cls not in CARE_TYPES:
            continue
        word_w = defaultdict(float)
        for feat, w in zip(feature_names, coefs[ci]):
            key = (feat or "").replace(" ", "")
            if not key:
                continue
            canon = _canonicalise(key)
            display = canon if canon else key
            word_w[display] += w
        top = sorted(word_w.items(), key=lambda kv: kv[1], reverse=True)[:15]
        out[cls] = [w for w, _ in top if len(w) >= 2]
    return out


# ---------------------------------------------------------------------------
# Second opinion (needs the LLM API; skipped otherwise)
# ---------------------------------------------------------------------------

def _second_opinion(records: list[dict]) -> list[dict]:
    from app.core.llm import is_llm_available
    from app.core.second_opinion import reconcile, run_second_opinion
    if not is_llm_available():
        return [{"note": "skipped - no LLM API key configured"}]
    rows = []
    sample = records[:10]
    agree = more = less = unavailable = 0
    for r in sample:
        ml_care = r["predicted_care_type"]
        ml_flags = r["ml_flags"] + r["rules_flags"]
        llm = run_second_opinion(r["text"], r["language"] or "en")
        recon = reconcile(ml_care, ml_flags, llm)
        note = recon["note"]
        if note == "agrees":
            agree += 1
        elif note == "llm_more_severe_asked":
            more += 1
        elif note == "llm_less_severe_ignored":
            less += 1
        else:
            unavailable += 1
        if note != "agrees":
            rows.append({
                "id": r["id"], "text": r["text"][:60],
                "ml_care_type": ml_care, "llm_care_type": recon.get("llm_care_type"),
                "note": note, "llm_reason": (llm or {}).get("reason", ""),
            })
    return [
        {"metric": "agreement_rate", "value": round(agree / max(len(sample), 1), 3),
         "n": len(sample), "agrees": agree, "more_severe": more, "less_severe": less,
         "unavailable": unavailable, "note": ""},
    ] + rows


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------

def _emergency_scoring(records: list[dict]) -> tuple[int, int, int]:
    """(a) immediate 112, (b) confirmation question (simulate Yes -> 112),
    (c) missed. A row is an emergency if it has a true flag or true care=112."""
    a = b = c = 0
    for r in records:
        is_em = bool(r["true_flags"]) or r["true_care_type"] == "emergency_112"
        if not is_em:
            continue
        if r["rules_flags"]:
            a += 1
        elif r["ml_flags"] or r["sem_flags"]:
            b += 1
        else:
            c += 1
    return a, b, c


def _allow_followup_false_eval(records: list[dict]) -> tuple[float, int, float, int]:
    correct = n = 0
    em_caught = em_total = 0
    for r in records:
        care, _, flags, _ = _full_predict(r["text"], r["language"] or "en", allow_followup=False)
        true_care = r["true_care_type"]
        if not true_care:
            continue
        n += 1
        pred = "emergency_112" if flags else care
        if pred == true_care:
            correct += 1
        if true_care == "emergency_112":
            em_total += 1
            if pred == "emergency_112":
                em_caught += 1
    acc = correct / n if n else 0.0
    em_rec = em_caught / em_total if em_total else 0.0
    return acc, n, em_rec, em_total


def _summary(datasets, per_dataset):
    header = ["metric", "dataset", "method", "n", "value", "wilson_lo", "wilson_hi", "honesty"]
    rows = [header]
    for ds in datasets:
        recs = per_dataset[ds["name"]]
        n = len(recs)
        correct = sum(1 for r in recs if r["correct"])
        acc = correct / n if n else 0.0
        lo, hi = _wilson(correct, n)
        honesty = "leaky - do not quote" if ds["leaky"] else "not leaky"
        rows.append(["routing_accuracy", ds["name"], "production ML", n, round(acc, 4),
                     round(lo, 4), round(hi, 4), honesty])
        em = _emergency_stats(recs)
        elo, ehi = _wilson(em["tp"], em["n_pos"])
        rows.append(["emergency_recall", ds["name"], "production ML", em["n_pos"],
                     round(em["recall"], 4), round(elo, 4), round(ehi, 4), honesty])
        fc, fn = _flag_detection_recall(recs)
        flo, fhi = _wilson(fc, fn)
        rows.append(["emergency_flag_detection_recall", ds["name"],
                     "rules + ML flags + semantic screen", fn, round(fc / fn, 4) if fn else 0.0,
                     round(flo, 4), round(fhi, 4), honesty])
        rows.append(["macro_f1", ds["name"], "production ML", n, round(_macro_f1(recs), 4),
                     "", "", honesty])
    # exact-text grouped CV (recorded at model selection; not refit here)
    if COMPARISON_JSON.exists():
        comp = json.loads(COMPARISON_JSON.read_text(encoding="utf-8"))
        model_a = comp.get("Model A: TF-IDF Char (2-5) + LR", {})
        if "exact_text_f1" in model_a:
            rows.append(["exact_text_grouped_cv_f1", "official (grouped CV)",
                         "recorded at selection", "", round(model_a["exact_text_f1"], 4),
                         "", "", "grouped CV (main figure, not leaky)"])
            rows.append(["exact_text_grouped_cv_accuracy", "official (grouped CV)",
                         "recorded at selection", "", round(model_a.get("accuracy", 0), 4),
                         "", "", "grouped CV (main figure, not leaky)"])
    # Override audit: final pipeline care_type vs raw ML argmax, per stage
    # (full pipeline conversations, offline; no thresholds tuned).
    try:
        from ml.audit_overrides import run_override_summary
        rows.extend(run_override_summary())
    except Exception as e:  # pragma: no cover - audit must never break the workbook
        rows.append(["override_audit", "", "skipped", "", "", "", "", f"error: {e}"])
    if not (DATA_DIR / "human_holdout.csv").exists():
        rows.append(["human_holdout", "human_holdout.csv", "skipped", "", "", "", "",
                     "missing - skipped"])

    # LLM mode: provider / model / latency (live DeepSeek) recorded once.
    from app.core.llm import llm_provider, llm_model, llm_fast_model
    rows.append(["llm_provider", "", "live self-test", "", llm_provider(), "", "", "config"])
    rows.append(["llm_model", "", "live self-test", "", llm_model(), "", "", "config"])
    rows.append(["llm_fast_model", "", "live self-test", "", llm_fast_model(), "", "", "config"])

    # Emergency scoring: (a) immediate 112, (b) confirmation question (simulate
    # Yes -> 112), (c) missed / routed non-emergency. Replaces the raw
    # "care-type emergency recall" number.
    for ds in datasets:
        recs = per_dataset[ds["name"]]
        a, b, c = _emergency_scoring(recs)
        n_em = a + b + c
        rows.append(["emergency_scoring_(a)_immediate_112", ds["name"], "rules", a, "", "", "",
                     "leaky - do not quote" if ds["leaky"] else "not leaky"])
        rows.append(["emergency_scoring_(b)_confirm_then_yes", ds["name"], "ML/semantic flags", b, "", "", "",
                     "leaky - do not quote" if ds["leaky"] else "not leaky"])
        rows.append(["emergency_scoring_(c)_missed", ds["name"], "none", c, "", "", "",
                     "leaky - do not quote" if ds["leaky"] else "not leaky"])
        if n_em:
            lo, hi = _wilson(a + b, n_em)
            rows.append(["emergency_recall_(a+b)", ds["name"], "rules + confirm-yes", n_em,
                         round((a + b) / n_em, 4), round(lo, 4), round(hi, 4),
                         "leaky - do not quote" if ds["leaky"] else "not leaky"])

    # allow_followup=false: best-guess decision on the non-leaky holdouts.
    for ds in ("redflag_holdout", "unseen_tests"):
        recs = per_dataset.get(ds, [])
        if not recs:
            continue
        acc, n_acc, em_rec, n_em = _allow_followup_false_eval(recs)
        rows.append(["allow_followup_false_accuracy", ds, "full pipeline (no followup)", n_acc,
                     round(acc, 4), *[round(x, 4) for x in _wilson(int(acc * n_acc), n_acc)], "not leaky"])
        rows.append(["allow_followup_false_emergency_recall", ds, "full pipeline (no followup)", n_em,
                     round(em_rec, 4), *[round(x, 4) for x in _wilson(int(em_rec * n_em), n_em)], "not leaky"])
    return rows


def _predictions_sheet(predictions):
    header = ["id", "text", "language", "true_care_type", "predicted_care_type"] + \
             [f"P({c})" for c in CARE_TYPES] + ["correct", "source_dataset"]
    rows = [header]
    for r in predictions:
        rows.append([
            r["id"], r["text"], r["language"], r["true_care_type"], r["predicted_care_type"],
        ] + [round(r["probs"].get(c, 0.0), 4) for c in CARE_TYPES] + [
            "" if r["correct"] is None else str(r["correct"]), r["source_dataset"],
        ])
    return rows


def _confusion_sheet(predictions):
    counts, norm = _build_confusion(predictions)
    header = ["true\\predicted"] + CARE_TYPES
    rows = [header]
    for i, c in enumerate(CARE_TYPES):
        rows.append([c] + counts[i])
    rows.append([])
    rows.append(["--- row-normalised ---"] + [""] * len(CARE_TYPES))
    for i, c in enumerate(CARE_TYPES):
        rows.append([c] + norm[i])
    return rows


def _errors_sheet(predictions):
    wrong = [r for r in predictions if r["correct"] is False]
    wrong.sort(key=lambda r: 0 if r["true_care_type"] == "emergency_112" else 1)
    header = ["id", "text", "true_care_type", "predicted_care_type", "source_dataset"]
    rows = [header]
    for r in wrong:
        rows.append([r["id"], r["text"][:80], r["true_care_type"], r["predicted_care_type"], r["source_dataset"]])
    return rows


def _redflags_sheet(predictions):
    header = ["flag", "positives", "caught_by_rules", "caught_by_ml", "caught_by_semantic",
              "missed", "false_alarms_on_negatives"]
    rows = [header]
    for flag in RED_FLAGS:
        pos = sum(1 for r in predictions if flag in r["true_flags"])
        c_rules = sum(1 for r in predictions if flag in r["true_flags"] and flag in r["rules_flags"])
        c_ml = sum(1 for r in predictions if flag in r["true_flags"] and flag in r["ml_flags"])
        c_sem = sum(1 for r in predictions if flag in r["true_flags"] and flag in r["sem_flags"])
        caught_any = sum(1 for r in predictions if flag in r["true_flags"] and
                         (flag in r["rules_flags"] or flag in r["ml_flags"] or flag in r["sem_flags"]))
        missed = pos - caught_any
        false_alarms = sum(1 for r in predictions if flag not in r["true_flags"] and
                           (flag in r["rules_flags"] or flag in r["ml_flags"] or flag in r["sem_flags"]))
        rows.append([flag, pos, c_rules, c_ml, c_sem, missed, false_alarms])
    return rows


def _features_sheet():
    top = _top_words_per_care_type()
    header = ["care_type"] + [f"word_{i + 1}" for i in range(15)]
    rows = [header]
    for c in CARE_TYPES:
        words = (top.get(c) or []) + [""] * 15
        rows.append([c] + words[:15])
    return rows


def _provenance_sheet(datasets):
    header = ["dataset", "rows", "unique_texts", "source", "human_reviewed", "use", "leaky"]
    rows = [header]
    for ds in datasets:
        recs = _load_csv(ds["path"])
        unique = len({(r.get("norm_input") or r.get("user_input") or "").strip() for r in recs})
        rows.append([ds["name"], len(recs), unique, ds["source"], ds["human_reviewed"],
                     ds["use"], "yes" if ds["leaky"] else "no"])
    rows.append(["human_holdout.csv", "", "", "human_holdout", "yes", "test",
                 "missing - skipped" if not (DATA_DIR / "human_holdout.csv").exists() else "no"])
    return rows


def _second_opinion_sheet(predictions):
    out = _second_opinion(predictions)
    header = ["id", "text", "ml_care_type", "llm_care_type", "note", "llm_reason"]
    rows = [header]
    for r in out:
        if "metric" in r:
            rows.append([r["metric"], "", "", "",
                         f"value={r.get('value')} n={r.get('n')} agrees={r.get('agrees')} "
                         f"more={r.get('more_severe')} less={r.get('less_severe')} "
                         f"unavail={r.get('unavailable')}", r.get("note", "")])
        else:
            rows.append([r.get("id", ""), r.get("text", ""), r.get("ml_care_type", ""),
                         r.get("llm_care_type", ""), r.get("note", ""), r.get("llm_reason", "")])
    return rows


# ---------------------------------------------------------------------------
# XLSX writer
# ---------------------------------------------------------------------------

def _write_sheet(wb, title, rows, freeze=True, wrong_col=None, note_rows=()):
    ws = wb.create_sheet(title)
    for row in rows:
        ws.append(row)
    if freeze:
        ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    if wrong_col is not None:
        for i, row in enumerate(rows[1:], start=2):
            if row[wrong_col] == "False":
                for cell in ws[i]:
                    cell.fill = _WRONG_FILL
    for width in range(1, len(rows[0]) + 1):
        ws.column_dimensions[get_column_letter(width)].width = 22
    return ws


def _write_csv(title, rows):
    path = RESULTS_DIR / f"verification_{title}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def _full_predict(text: str, lang: str, allow_followup: bool = True):
    """Full production pipeline (rules + ML + local screen, LLM off for
    determinism). Returns (care_type, urgency, red_flags, confidence)."""
    from unittest.mock import patch
    from app.core.pipeline import run_triage_pipeline
    from app.schemas import Location as _Loc, TriageRequest as _Req
    with patch("app.core.pipeline.run_second_opinion", return_value=None), \
            patch("app.core.pipeline.screen_red_flags", return_value={"status": "skip", "flags": [], "combined": False}):
        resp = run_triage_pipeline(_Req(
            user_input=text, language=lang, allow_followup=allow_followup,
            context_consent=False, location=_Loc(lat=28.54, lng=77.27),
        ))
    return (resp.care_type, resp.urgency, resp.red_flags, resp.confidence)


def _write_predictions_csv(predictions):
    """Official hackathon format: id + label columns (care_type, urgency, red_flags).

    Produced in allow_followup=false mode so every row has a label (best-guess
    decision). Per the problem statement, a non-empty red_flags list means
    care_type=emergency_112 / urgency=emergency.
    """
    rows = []
    for r in predictions:
        if r["source_dataset"] not in ("unseen_tests", "redflag_holdout"):
            continue
        care_type, urgency, red_flags, _ = _full_predict(r["text"], r["language"] or "en", allow_followup=False)
        if red_flags:
            care_type, urgency = "emergency_112", "emergency"
        rows.append([r["id"], care_type or "teleconsultation", urgency or "same_day", ";".join(sorted(set(red_flags)))])
    with open(PREDICTIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "care_type", "urgency", "red_flags"])
        writer.writerows(rows)
    return len(rows)


# ---------------------------------------------------------------------------

def main():
    from app.config import settings as _s
    # Disable the LLM for the deterministic ML evaluation (fast + reproducible);
    # the SecondOpinion sheet re-enables it for the live disagreement rate.
    _orig_key = _s.DEEPSEEK_API_KEY
    _s.DEEPSEEK_API_KEY = ""
    _s.LLM_ROLE = "off"

    datasets, predictions, per_dataset = _evaluate()

    sheets = [
        ("Summary", _summary(datasets, per_dataset)),
        ("Predictions", _predictions_sheet(predictions)),
        ("Confusion", _confusion_sheet(predictions)),
        ("Errors", _errors_sheet(predictions)),
        ("RedFlags", _redflags_sheet(predictions)),
        ("Features", _features_sheet()),
        ("Provenance", _provenance_sheet(datasets)),
    ]
    _s.DEEPSEEK_API_KEY = _orig_key
    _s.LLM_ROLE = "second_opinion"
    sheets.append(("SecondOpinion", _second_opinion_sheet(predictions)))

    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets:
        wrong_col = rows[0].index("correct") if title == "Predictions" and "correct" in rows[0] else None
        _write_sheet(wb, title, rows, wrong_col=wrong_col)
    wb.save(XLSX)

    for title, rows in sheets:
        _write_csv(title, rows)

    n_pred = _write_predictions_csv(predictions)

    print(f"Wrote {XLSX}")
    print(f"Wrote CSVs to {RESULTS_DIR}")
    print(f"Wrote {n_pred} rows to {PREDICTIONS_CSV}")
    print(f"Evaluated {len(predictions)} rows across {len(datasets)} datasets")


if __name__ == "__main__":
    main()
