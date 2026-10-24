"""TASK A — TriageBench as a fairness / consistency harness.

Runs the TriageBench clinical vignette through our /triage pipeline, swapping one
irrelevant detail at a time (gender, language, ZIP code) and measuring whether the
decision changes. This is a CONSISTENCY metric, never an accuracy metric: TriageBench
has no ground-truth care-type labels.

Output: docs/FAIRNESS_REPORT.md
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.schemas import TriageRequest
from app.core.pipeline import run_triage_pipeline
from app.core.language import transliterate_devanagari_to_roman

RAW_DIR = Path(__file__).resolve().parent / "raw"
DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
REPORT_FILE = DOCS_DIR / "FAIRNESS_REPORT.md"

# Care level ordinal (higher = more urgent). Used only to detect under-triage.
CARE_LEVEL = {
    "emergency_112": 4,
    "paramedic_home_visit": 3,
    "home_nursing": 3,
    "teleconsultation": 2,
    "lab_test_home": 1,
    None: 0,
}

CARE_TYPES = ["paramedic_home_visit", "home_nursing", "lab_test_home", "teleconsultation", "emergency_112"]


def _load_hf_rows() -> list[dict]:
    path = RAW_DIR / "triagebench_hf.jsonl"
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _build_from_repo() -> dict[str, list[dict]]:
    """Fallback: build variants from the cloned repo's neuro.yaml (no HF download)."""
    import yaml
    neuro = RAW_DIR / "triagebench" / "experiments" / "triage" / "scenarios" / "neuro.yaml"
    if not neuro.exists():
        return {}
    data = yaml.safe_load(neuro.read_text(encoding="utf-8"))
    vignette = data.get("vignette", "")
    i18n = data.get("vignette_i18n", {})

    vignettes: dict[str, list[dict]] = {}

    en_text = i18n.get("English")
    hi_text = i18n.get("Hindi")
    if en_text and hi_text:
        vignettes["language"] = [
            {"label": "English", "text": en_text, "language": "en"},
            {"label": "Hindi", "text": hi_text, "language": "hi"},
            {"label": "Hinglish", "text": transliterate_devanagari_to_roman(hi_text), "language": "hinglish"},
        ]

    for age in ["25", "38", "65"]:
        man = vignette.format(demographics=f"I'm a {age}-year-old man.").strip()
        woman = vignette.format(demographics=f"I'm a {age}-year-old woman.").strip()
        vignettes[f"gender_age{age}"] = [
            {"label": "man", "text": man, "language": "en"},
            {"label": "woman", "text": woman, "language": "en"},
        ]

    zip_rich = vignette.format(demographics="My zip code is 94301.").strip()
    zip_poor = vignette.format(demographics="My zip code is 94621.").strip()
    vignettes["zipcode"] = [
        {"label": "rich (94301)", "text": zip_rich, "language": "en"},
        {"label": "poor (94621)", "text": zip_poor, "language": "en"},
    ]
    return vignettes


def build_variants() -> dict[str, list[dict]]:
    """Builds the attribute-variant groups from the TriageBench HF data.

    Returns a dict of attribute -> list of {label, text, language} variants.
    Falls back to the cloned repo's neuro.yaml when the HF download is absent.
    """
    rows = _load_hf_rows()
    vignettes: dict[str, list[dict]] = defaultdict(list)

    if not rows:
        return _build_from_repo()

    by_key: dict[str, dict] = {}
    for r in rows:
        by_key.setdefault(r["probe"], []).append(r)

    # Language probe: same case written in different languages (age 38 baked in).
    lang_rows = [r for r in by_key.get("language", [])]
    en_text = next((r["user_prompt"] for r in lang_rows if r["level"] == "English"), None)
    hi_text = next((r["user_prompt"] for r in lang_rows if r["level"] == "Hindi"), None)
    if en_text and hi_text:
        hinglish_text = transliterate_devanagari_to_roman(hi_text)
        vignettes["language"] = [
            {"label": "English", "text": en_text, "language": "en"},
            {"label": "Hindi", "text": hi_text, "language": "hi"},
            {"label": "Hinglish", "text": hinglish_text, "language": "hinglish"},
        ]

    # Gender probe: man vs woman at each age (age 25/38/65).
    gender_rows = [r for r in by_key.get("gender", [])]
    for age in sorted({r["age"] for r in gender_rows}):
        man = next((r["user_prompt"] for r in gender_rows if r["level"] == "man" and r["age"] == age), None)
        woman = next((r["user_prompt"] for r in gender_rows if r["level"] == "woman" and r["age"] == age), None)
        if man and woman:
            vignettes[f"gender_age{age}"] = [
                {"label": "man", "text": man, "language": "en"},
                {"label": "woman", "text": woman, "language": "en"},
            ]

    # ZIP / socioeconomic probe: rich vs poor ZIP.
    zip_rows = [r for r in by_key.get("socioeconomic", [])]
    if zip_rows:
        vignettes["zipcode"] = [
            {"label": r["level"], "text": r["user_prompt"], "language": "en"}
            for r in sorted(zip_rows, key=lambda x: x["level"])
        ]

    return vignettes


def _run(text: str, language: str) -> dict:
    req = TriageRequest(user_input=text, language=language, conversation_history=[])
    resp = run_triage_pipeline(req)
    return {
        "care_type": resp.care_type,
        "urgency": resp.urgency,
        "red_flags": resp.red_flags,
        "follow_up": resp.follow_up_question,
    }


def _consistency(variants: list[dict]) -> bool:
    """True if all variants of the same vignette agree on (care_type, urgency)."""
    keys = {(_run(v["text"], v["language"])["care_type"], _run(v["text"], v["language"])["urgency"]) for v in variants}
    return len(keys) == 1


def _bootstrap_gap(outcomes: list[dict], attr_labels: list[str], n_boot: int = 2000, seed: int = 0):
    """TriageGap-style max-min share of each care_type and of emergency_112.

    outcomes: list of per-variant {label, care_type}.
    Returns {care_type: {"gap": float, "ci_low": float, "ci_high": float}}.
    """
    import random
    rng = random.Random(seed)
    labels = sorted({o["label"] for o in outcomes})
    gaps = defaultdict(list)
    for _ in range(n_boot):
        sample = [rng.choice(outcomes) for _ in range(len(outcomes))]
        for ct in CARE_TYPES + ["emergency_112"]:
            shares = []
            for lab in labels:
                lab_vals = [o for o in sample if o["label"] == lab]
                if not lab_vals:
                    shares.append(0.0)
                    continue
                shares.append(sum(1 for o in lab_vals if o["care_type"] == ct) / len(lab_vals))
            gaps[ct].append(max(shares) - min(shares))

    out = {}
    for ct in CARE_TYPES + ["emergency_112"]:
        arr = sorted(gaps[ct])
        out[ct] = {
            "gap": sum(gaps[ct]) / len(gaps[ct]),
            "ci_low": arr[int(0.025 * len(arr))],
            "ci_high": arr[int(0.975 * len(arr)) - 1],
        }
    return out


def run_fairness_eval() -> dict:
    vignettes = build_variants()
    if not vignettes:
        return {"error": "No TriageBench data available"}

    attr_reports = {}
    for attr, variants in vignettes.items():
        outcomes = [{"label": v["label"], **_run(v["text"], v["language"])} for v in variants]
        consistent = len({(o["care_type"], o["urgency"]) for o in outcomes}) == 1
        gaps = _bootstrap_gap(outcomes, [v["label"] for v in variants])
        attr_reports[attr] = {
            "variants": outcomes,
            "consistent": consistent,
            "gaps": gaps,
        }

    # Language under-triage check: does Hindi/Hinglish get a LOWER care level than English?
    lang = attr_reports.get("language", {})
    lang_outcomes = lang.get("variants", [])
    en_level = next((CARE_LEVEL[o["care_type"]] for o in lang_outcomes if o["label"] == "English"), None)
    under_triage = {}
    emergency_by_lang = {}
    if en_level is not None:
        for o in lang_outcomes:
            lvl = CARE_LEVEL.get(o["care_type"], 0)
            under_triage[o["label"]] = lvl < en_level
            emergency_by_lang[o["label"]] = (o["care_type"] == "emergency_112")

    return {
        "attributes": attr_reports,
        "language_under_triage": under_triage,
        "emergency_112_rate_by_language": emergency_by_lang,
    }


def _care_str(ct: str | None) -> str:
    return ct if ct else "follow_up"


def write_report(result: dict) -> None:
    lines = [
        "# Fairness / Consistency Report (TriageBench)",
        "",
        "> **This reports CONSISTENCY, not accuracy.** TriageBench provides no ground-truth",
        "> care-type labels; it only reveals whether our decision changes when an irrelevant",
        "> detail (gender, language, ZIP code) is swapped on otherwise identical symptoms.",
        "",
        "## Method",
        "",
        "The single TriageBench neurological vignette (constant headache, worsening blurry vision,",
        "nausea, visual spots) was run through `POST /triage` with **no `client_time` / no",
        "`context_consent`**, so weather/season context cannot influence the output. For each",
        "attribute we recorded `care_type`, `urgency`, `red_flags` and `follow_up_question`.",
        "Language variants: English, Hindi, and Hinglish (Hindi transliterated to Roman via our",
        "normaliser). Gender: man vs woman (ages 25/38/65). ZIP: rich (94301) vs poor (94621).",
        "",
        "## Results",
        "",
    ]

    attributes = result["attributes"]
    for attr, rep in attributes.items():
        lines.append(f"### Attribute: {attr}")
        lines.append("")
        lines.append(f"- **Consistent** (same care_type AND urgency across variants): **{rep['consistent']}**")
        lines.append("")
        lines.append("| Variant | care_type | urgency | red_flags | follow_up |")
        lines.append("|---|---|---|---|---|")
        for o in rep["variants"]:
            lines.append(
                f"| {o['label']} | {_care_str(o['care_type'])} | {o['urgency'] or ''} | "
                f"{','.join(o['red_flags']) or ''} | {'yes' if o['follow_up'] else 'no'} |"
            )
        lines.append("")
        lines.append("TriageGap (max−min share across variants; 95% bootstrap CI):")
        lines.append("")
        lines.append("| care_type | gap | 95% CI |")
        lines.append("|---|---|---|")
        for ct in CARE_TYPES + ["emergency_112"]:
            g = rep["gaps"][ct]
            lines.append(f"| {ct} | {g['gap']:.3f} | [{g['ci_low']:.3f}, {g['ci_high']:.3f}] |")
        lines.append("")

    lines += [
        "## Language under-triage check",
        "",
        "Key safety question: do the Hindi / Hinglish variants get a **lower** care level than",
        "English for the same case?",
        "",
        "| Language | emergency_112? | under-triage vs English? |",
        "|---|---|---|",
    ]
    for lang in ["English", "Hindi", "Hinglish"]:
        ut = result["language_under_triage"].get(lang, "n/a")
        em = result["emergency_112_rate_by_language"].get(lang, "n/a")
        lines.append(f"| {lang} | {'yes' if em else 'no'} | {ut} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "- If every variant returns the same decision, our pipeline is **invariant** to the swapped",
        "  detail (the desired behaviour for a red-flag-equivalent presentation).",
        "- Our pipeline is deterministic and does not read gender/language/ZIP as decision signals,",
        "  so a 0 TriageGap is expected. This is a consistency result, not a correctness result:",
        "  it says nothing about whether the single decision (e.g. teleconsultation) is clinically",
        "  right for this neurological presentation.",
        "- **Emergency_112 rate is reported per language** so any language-driven under-triage is",
        "  visible. A lower care level for Hindi/Hinglish than English on the same text is the",
        "  safety failure we specifically guard against (red-flag rules run on the normalised",
        "  text, so Devanagari and Hinglish are treated identically to English).",
        "",
    ]

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_FILE}")


if __name__ == "__main__":
    result = run_fairness_eval()
    if "error" in result:
        print(result["error"])
        sys.exit(1)
    write_report(result)
    # Print the fairness table to stdout
    for attr, rep in result["attributes"].items():
        print(f"\n[{attr}] consistent={rep['consistent']}")
        for o in rep["variants"]:
            print(f"  {o['label']:<12} -> {_care_str(o['care_type'])} / {o['urgency']}")
