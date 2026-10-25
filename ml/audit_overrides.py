"""Override audit: how often the final pipeline care_type differs from the
raw ML argmax, which stage changed it, and whether each override helped or
hurt accuracy.

Runs three sets through the full pipeline as the app would drive it:
conversations continue while the pipeline asks a CLOSED red-flag screen
question (answered truthfully: "Yes" only when the true label is
emergency_112, and the injury module's head_hit question likewise), and stop
when the pipeline asks for information we cannot answer truthfully (module
cards, intake questions, "no symptoms recognised") — those rows are counted
as "undecided / needs follow-up", never answered with fabricated facts.
Offline mode (LLM disabled): the LLM second opinion never changes care_type,
so the deterministic stages are exactly what is being audited.

  1. ml/data/unseen_tests.csv            (30 rows, raw = production model argmax)
  2. ml/data/redflag_holdout.csv         (53 rows, raw = production model argmax)
  3. official triage_dataset.jsonl       (raw = exact-text grouped CV
     out-of-fold prediction, the honest "raw model on its own" estimate
     recomputed exactly as in compare_models.py: StratifiedGroupKFold on
     exact normalized text, seed 42, TF-IDF char (2-5) + LR C=2.0 balanced)

No thresholds are tuned here. Outputs:
  - console report
  - ml/results/override_audit.json
  - ml/results/override_audit_rows.csv (per-row trail)
  - Summary rows are appended to ml/results/verification.xlsx via
    ml/make_verification_workbook.py (run_override_summary()).
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

from app.schemas import TriageRequest, Location, ChatMessage
from app.core.pipeline import run_triage_pipeline
from app.core.triage_model import raw_model_argmax
from app.core.language import normalise_text
from app.core.intake import extract_slots, build_classifier_text, is_bank_question
from app.core.guardrails import input_guard
from app.core.semantic_screen import QUESTION_TO_FLAG, COMBINED_QUESTION_ID, WHICH_ONE_QUESTION_ID

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR = BASE_DIR.parent / "docs"

UNSEEN = DATA_DIR / "unseen_tests.csv"
HOLDOUT = DATA_DIR / "redflag_holdout.csv"
OFFICIAL = DATA_DIR / "official" / "triage_dataset.jsonl"

LOC = Location(lat=28.54, lng=77.27)
MAX_TURNS = 6

_LANG_MAP = {"English": "en", "Hindi": "hi", "Hinglish": "hinglish",
             "en": "en", "hi": "hi", "hinglish": "hinglish"}

STAGE_LABELS = {
    "0_model_version": "Production model differs from CV fold model (not a pipeline stage)",
    "2_red_flag_bypass": "Stage 2 red-flag emergency bypass (rules)",
    "2_pregnancy_layer": "Stage 2.2 pregnancy layer",
    "2_semantic_screen_yes": "Stage 2.3/2.4 semantic screen confirmation",
    "2_module_decision": "Module decision (injury module: head hit -> emergency)",
    "5_hybrid_rules_ml": "Stage 5 rule layer (inside predict_triage)",
    "5_unfamiliar_map": "Stage 5 unfamiliar-care-type mapping",
    "6_risk_modifiers": "Stage 6 risk modifiers",
    "6.5_ambulatory": "Stage 6.5 ambulatory adjustment",
    "6.6_injury_sanity": "Stage 6.6 injury sanity",
    "7_confidence_fallback": "Stage 7 confidence fallback",
    "8_emergency_rule2": "Stage 8 emergency rule (Rule 2)",
    "8_emergency_remap": "Stage 8 emergency remap (not-emergency)",
    "8_pregnancy_floor": "Stage 8 pregnancy floor",
    "8_context_night_rain": "Stage 8 context night/rain",
}

_SCREEN_QUESTION_IDS = set(QUESTION_TO_FLAG.keys()) | {COMBINED_QUESTION_ID, WHICH_ONE_QUESTION_ID}


def load_official_clf_entries():
    entries = []
    with open(OFFICIAL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            req = item.get("request", {})
            resp = item.get("response", {})
            raw = (req.get("user_input") or "").strip()
            norm = normalise_text(raw)
            if not norm:
                continue
            entries.append({
                "id": item.get("id"),
                "user_input": raw,
                "norm_text": norm,
                "language": item.get("detected_language") or req.get("language") or "English",
                "care_type": resp.get("care_type"),
            })
    return [e for e in entries if e.get("care_type")]


def exact_text_cv_oof(entries):
    """Replicates compare_models.py's exact-text grouped CV for Model A and
    returns the out-of-fold prediction per entry (the honest raw-model
    estimate on training data)."""
    texts = [e["norm_text"] for e in entries]
    labels = [e["care_type"] for e in entries]
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold

    text_to_grp = {t: i for i, t in enumerate(sorted(set(texts)))}
    exact_groups = np.array([text_to_grp[t] for t in texts])
    sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    oof = np.empty(len(texts), dtype=object)
    for tr, val in sgkf.split(texts, labels, groups=exact_groups):
        vec = TfidfVectorizer(ngram_range=(2, 5), analyzer="char", min_df=1, sublinear_tf=True)
        x_tr = vec.fit_transform([texts[i] for i in tr])
        x_v = vec.transform([texts[i] for i in val])
        clf = LogisticRegression(C=2.0, class_weight="balanced", max_iter=500, random_state=42)
        clf.fit(x_tr, [labels[i] for i in tr])
        oof[val] = clf.predict(x_v)
    return [str(p) for p in oof]


def run_conversation(user_input, lang, true_label):
    """Drives the pipeline like the app. Returns
    (final_care_type, overrides_of_last_turn, debug_of_last_turn, stop_reason)."""
    history: list[ChatMessage] = []
    last_resp = None
    last_debug = None
    module_id = None
    module_answers: dict = {}
    current = user_input
    for _turn in range(MAX_TURNS):
        last_resp = run_triage_pipeline(
            TriageRequest(
                user_input=current, language=lang, location=LOC, conversation_history=history,
                module_id=module_id, module_answers=module_answers if module_answers else None,
            ),
            debug=True,
        )
        last_debug = last_resp.debug or {}
        if last_resp.care_type is not None:
            return last_resp.care_type, last_debug.get("overrides") or [], last_debug, None

        q_text = last_resp.follow_up_question or ""
        card = last_resp.module_card
        if card is not None:
            field = (card.get("fields") or [{}])[0]
            if card.get("module_id") == "injury" and field.get("id") == "head_hit":
                module_id = card.get("module_id")
                module_answers[field.get("id")] = "Yes" if true_label == "emergency_112" else "No"
                answer = module_answers[field.get("id")]
            else:
                # Module fields other than head_hit cannot be answered
                # truthfully from the dataset; stop instead of fabricating.
                return None, [], last_debug, "module_card"
        elif q_text:
            qid = is_bank_question(q_text)
            if qid == WHICH_ONE_QUESTION_ID:
                answer = (last_resp.follow_up_options or ["Yes"])[0]
            elif qid in _SCREEN_QUESTION_IDS:
                answer = "Yes" if true_label == "emergency_112" else "No"
            else:
                return None, [], last_debug, "intake_question"
        else:
            return None, [], last_debug, "no_question"

        history.append(ChatMessage(role="assistant", text=q_text, content=q_text))
        history.append(ChatMessage(role="user", text=answer, content=answer))
        current = answer
    return None, [], last_debug, "max_turns"


def replicated_raw_argmax(user_input):
    """Raw production-model argmax computed exactly the way the pipeline
    builds its classifier text (used for rows that emergency-bypass stage 5,
    where the pipeline itself never ran the model)."""
    cleaned = input_guard(user_input)["cleaned_text"]
    norm = normalise_text(cleaned)
    slots = extract_slots(norm, [])
    return raw_model_argmax(build_classifier_text(slots))


def production_argmax_from_debug(overrides, user_input):
    for o in overrides:
        if o.get("stage") == "5_model_argmax":
            return o.get("care_type")
    return replicated_raw_argmax(user_input)


def attributing_stage(overrides, final, raw, raw_prod, debug):
    """The stage responsible for the final deviation from the raw argmax."""
    if raw and raw_prod and raw != raw_prod and (final == raw or final == raw_prod):
        # The difference comes from the deployed model itself differing from
        # the CV fold model that produced `raw`; no pipeline stage is
        # responsible.
        return "0_model_version"
    for o in reversed(overrides):
        if o.get("to") == final:
            return o.get("stage")
    if final == raw:
        return None
    debug = debug or {}
    if debug.get("module_id"):
        return "2_module_decision"
    reasons_str = " | ".join(debug.get("reasons") or [])
    if "Semantic screen" in reasons_str:
        return "2_semantic_screen_yes"
    if "Pregnancy layer" in reasons_str:
        return "2_pregnancy_layer"
    if "red flag" in reasons_str.lower() or "emergency bypass" in reasons_str:
        return "2_red_flag_bypass"
    # The stage-5 hybrid already equals the final: the rule layer inside
    # predict_triage produced it.
    return "5_hybrid_rules_ml"


def evaluate(name, rows, raw_of):
    stats = {
        "name": name,
        "n_rows": len(rows),
        "n_decided": 0,
        "n_undecided": 0,
        "undecided_reasons": Counter(),
        "n_labeled_decided": 0,
        "n_override": 0,
        "n_override_prod": 0,
        "n_override_labeled": 0,
        "override_fixed": 0,
        "override_broke": 0,
        "override_both_wrong": 0,
        "pipeline_correct": 0,
        "raw_correct": 0,
        "stage_transitions": Counter(),
        "stage_attribution": Counter(),
        "rows": [],
    }
    for i, row in enumerate(rows):
        final, overrides, debug, stop_reason = run_conversation(
            row["user_input"], _LANG_MAP.get(row.get("language", "en"), "en"),
            row.get("care_type"),
        )
        raw = raw_of(i, overrides, row)
        true = row.get("care_type") or ""
        if final is None:
            stats["n_undecided"] += 1
            stats["undecided_reasons"][stop_reason or "unknown"] += 1
            stats["rows"].append({
                "id": row.get("id"), "user_input": row["user_input"],
                "raw_ml": raw or "", "raw_prod": raw or "", "final": "",
                "true_label": true, "override": "", "stage": stop_reason or "undecided",
                "outcome": "",
            })
            continue
        stats["n_decided"] += 1
        for o in overrides:
            if o.get("from") and o.get("to") and o.get("from") != o.get("to"):
                stats["stage_transitions"][o.get("stage")] += 1
        raw_prod = production_argmax_from_debug(overrides, row["user_input"])
        override = bool(raw is not None and final != raw)
        override_prod = bool(raw_prod is not None and final != raw_prod)
        stage = ""
        outcome = ""
        if override:
            stats["n_override"] += 1
            stage = attributing_stage(overrides, final, raw, raw_prod, debug)
            stats["stage_attribution"][stage] += 1
        if override_prod:
            stats["n_override_prod"] += 1
        if true:
            stats["n_labeled_decided"] += 1
            if final == true:
                stats["pipeline_correct"] += 1
            if raw is not None and raw == true:
                stats["raw_correct"] += 1
            if override:
                stats["n_override_labeled"] += 1
                if final == true:
                    stats["override_fixed"] += 1
                    outcome = "fixed"
                elif raw == true:
                    stats["override_broke"] += 1
                    outcome = "broke"
                else:
                    stats["override_both_wrong"] += 1
                    outcome = "both_wrong"
        stats["rows"].append({
            "id": row.get("id"), "user_input": row["user_input"],
            "raw_ml": raw or "", "raw_prod": raw_prod or "", "final": final,
            "true_label": true, "override": "1" if override else "",
            "stage": stage, "outcome": outcome,
        })
    stats["override_rate"] = (stats["n_override"] / stats["n_decided"]) if stats["n_decided"] else None
    stats["override_rate_prod"] = (stats["n_override_prod"] / stats["n_decided"]) if stats["n_decided"] else None
    stats["pipeline_acc"] = (stats["pipeline_correct"] / stats["n_labeled_decided"]) if stats["n_labeled_decided"] else None
    stats["raw_acc"] = (stats["raw_correct"] / stats["n_labeled_decided"]) if stats["n_labeled_decided"] else None
    return stats


def update_workbook(report, stage_labels):
    """REMOVED: override summary rows are now appended to the Summary sheet of
    ml/results/verification.xlsx by ml/make_verification_workbook.py via
    run_override_summary()."""
    raise NotImplementedError


_REPORT_CACHE: dict | None = None


def _compute_report() -> dict:
    """Runs the full override audit (offline) and returns the report dict.
    Cached per process so make_verification_workbook and main() share one run."""
    global _REPORT_CACHE
    if _REPORT_CACHE is not None:
        return _REPORT_CACHE

    prev_key = settings.DEEPSEEK_API_KEY
    settings.DEEPSEEK_API_KEY = ""  # offline: the LLM second opinion never changes care_type
    try:
        unseen = []
        with open(UNSEEN, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                unseen.append({"id": r["id"], "user_input": r["user_input"],
                               "language": r.get("language", "en"), "care_type": r["care_type"]})
        holdout = []
        with open(HOLDOUT, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                holdout.append({"id": r["id"], "user_input": r["user_input"],
                                "language": r.get("language", "en"), "care_type": r["care_type"]})
        official = load_official_clf_entries()
        print(f"Official rows (labeled, exact-text CV set): {len(official)}")
        cv_oof = exact_text_cv_oof(official)
        oof_by_idx = dict(enumerate(cv_oof))

        def raw_prod_only(i, overrides, row):
            return production_argmax_from_debug(overrides, row["user_input"])

        def raw_cv_oof(i, overrides, row):
            return oof_by_idx[i]

        datasets = [
            ("unseen_tests.csv", unseen, raw_prod_only),
            ("redflag_holdout.csv", holdout, raw_prod_only),
            ("official_triage (exact-text CV OOF raw)", official, raw_cv_oof),
        ]

        print("\nRunning pipeline conversations (offline, truthful screen answers only)...\n")
        report = {"datasets": [], "stages": {}, "all": {}}
        all_decided = 0
        all_override = 0
        transitions_total = Counter()
        attribution_total = Counter()
        rows_all = []
        for name, rows, raw_of in datasets:
            print(f"  {name}: {len(rows)} rows")
            stats = evaluate(name, rows, raw_of)
            report["datasets"].append(stats)
            rows_all.extend((name, r) for r in stats["rows"])
            all_decided += stats["n_decided"]
            all_override += stats["n_override"]
            transitions_total.update(stats["stage_transitions"])
            attribution_total.update(stats["stage_attribution"])
            print(f"    decided={stats['n_decided']} undecided={stats['n_undecided']} "
                  f"{dict(stats['undecided_reasons'])} "
                  f"override_rate={stats['override_rate']:.3f} "
                  f"pipeline_acc={stats['pipeline_acc']:.3f} raw_acc={stats['raw_acc']:.3f}")

        report["all"] = {
            "n_decided": all_decided,
            "n_override": all_override,
            "override_rate": (all_override / all_decided) if all_decided else None,
        }
        report["stages"] = {k: {"transitions": transitions_total.get(k, 0),
                                "attributed_overrides": attribution_total.get(k, 0)}
                            for k in STAGE_LABELS}
        report["_rows"] = rows_all
    finally:
        settings.DEEPSEEK_API_KEY = prev_key
    _REPORT_CACHE = report
    return report


def run_override_summary() -> list[list]:
    """Summary-sheet rows for ml/results/verification.xlsx: the override rate
    per dataset and the per-stage override counts, in the workbook's
    (metric, dataset, method, n, value, wilson_lo, wilson_hi, honesty) layout."""
    report = _compute_report()
    blank = [""] * 8
    rows: list[list] = [
        blank,
        ["override_rate (final != raw ML argmax)", "", "full pipeline vs raw ML argmax",
         "", "", "", "", "see per-dataset rows"],
    ]
    for d in report["datasets"]:
        honesty = "not leaky" if "official" not in d["name"] else "in-sample rows (leaky for accuracy)"
        rows.append(["override_rate", d["name"], "full pipeline vs raw ML argmax",
                     d["n_decided"], round(d["override_rate"], 4), "", "", honesty])
    all_d = report["all"]
    rows.append(["override_rate", "ALL (3 sets)", "full pipeline vs raw ML argmax",
                 all_d["n_decided"], round(all_d["override_rate"], 4), "", "",
                 "per-dataset honesty above"])
    for k, label in STAGE_LABELS.items():
        a = report["stages"][k]["attributed_overrides"]
        if a:
            rows.append(["override_stage_count", k, label, a, "", "", "", ""])
    fixed = sum(d["override_fixed"] for d in report["datasets"])
    broke = sum(d["override_broke"] for d in report["datasets"])
    rows.append(["override_outcome", "fixed", "override corrected a raw-model error",
                 fixed, "", "", "", ""])
    rows.append(["override_outcome", "broke", "override broke a correct raw decision",
                 broke, "", "", "", ""])
    return rows


def main():
    report = _compute_report()
    rows_all = report.pop("_rows", [])

    all_d = report["all"]
    print("\n" + "=" * 100)
    print("OVERRIDE AUDIT REPORT")
    print("=" * 100)
    print(f"\nOverall override rate: {all_d['n_override']}/{all_d['n_decided']} decided rows "
          f"({all_d['override_rate']:.3f})")
    print("\nPer-dataset:")
    for d in report["datasets"]:
        print(f"  {d['name']:44s} rows={d['n_rows']:>4} decided={d['n_decided']:>4} "
              f"override={d['n_override']:>4} ({d['override_rate']:.3f}) "
              f"override_vs_deployed={d['n_override_prod']:>4} ({d['override_rate_prod']:.3f}) "
              f"pipeline_acc={d['pipeline_acc']:.3f} raw_acc={d['raw_acc']:.3f}")
    print("\nPer-stage (transitions = rows where the stage changed care_type;")
    print("attributed = overrides whose final value came from that stage):")
    for k, label in STAGE_LABELS.items():
        t, a = report["stages"][k]["transitions"], report["stages"][k]["attributed_overrides"]
        if t or a:
            print(f"  {k:26s} {label:44s} transitions={t:>3} attributed={a:>3}")
    print("\nOverride correctness vs true label (labeled overrides):")
    for d in report["datasets"]:
        print(f"  {d['name']:44s} fixed={d['override_fixed']:>3} broke={d['override_broke']:>3} "
              f"both_wrong={d['override_both_wrong']:>3} (of {d['n_override_labeled']} labeled)")

    with open(RESULTS_DIR / "override_audit.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nSaved ml/results/override_audit.json")

    with open(RESULTS_DIR / "override_audit_rows.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "id", "user_input", "raw_ml", "raw_prod", "final", "true_label",
                    "override", "attributed_stage", "override_outcome"])
        for ds_name, r in rows_all:
            w.writerow([ds_name, r["id"], r["user_input"], r["raw_ml"], r["raw_prod"],
                        r["final"], r["true_label"], r["override"], r["stage"], r["outcome"]])
    print("Saved ml/results/override_audit_rows.csv")
    print("Override summary rows are written to verification.xlsx by ml/make_verification_workbook.py")


if __name__ == "__main__":
    main()
