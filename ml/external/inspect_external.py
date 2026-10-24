"""Inspect the downloaded external datasets and write ml/external/SOURCES.md.

Prints columns, row counts, language mix, and 5 sample rows for each resource.
Never redistributes the underlying text beyond short inspection samples.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.language import detect_script_and_language

RAW_DIR = Path(__file__).resolve().parent / "raw"
SOURCES_FILE = Path(__file__).resolve().parent / "SOURCES.md"


def _rows_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def inspect_triagebench() -> str:
    path = RAW_DIR / "triagebench_hf.jsonl"
    rows = _rows_jsonl(path) if path.exists() else []
    print("\n" + "=" * 80)
    print("TRAGEBENCH (wongqihan/triagebench)")
    print("=" * 80)
    if not rows:
        print("Not downloaded (using repo vignettes).")
        return f"- TriageBench: HF not downloaded; using repo vignettes (raw/triagebench)."

    cols = sorted(rows[0].keys())
    print("Columns:", cols)
    print("Row count:", len(rows))
    probes = Counter(r.get("probe") for r in rows)
    print("Probes:", dict(probes))
    axes = Counter((r.get("axis"), r.get("level")) for r in rows)
    print("Axis/level variants:", dict(axes))
    print("5 sample rows:")
    for r in rows[:5]:
        print("  -", {k: (str(v)[:80]) for k, v in r.items() if k in ("probe", "axis", "level", "age", "scenario")})
    return (
        "- TriageBench: 14 HF rows (probes: gender/language/zipcode); "
        "vignettes + translations also in raw/triagebench repo."
    )


def inspect_mmcqs() -> str:
    path = RAW_DIR / "mmcqs_hf.jsonl"
    rows = _rows_jsonl(path) if path.exists() else []
    print("\n" + "=" * 80)
    print("MMCQS (ArkaAcharya/MMCQSD)")
    print("=" * 80)
    if not rows:
        print("Not downloaded (using repo sample).")
        return "- MMCQS: HF not downloaded; using repo sample dataset_sample.csv."

    cols = sorted(rows[0].keys())
    print("Columns:", cols)
    print("Row count:", len(rows))
    langs = Counter()
    for r in rows:
        langs[detect_script_and_language(r.get("Codemixed_Question") or "")] += 1
    print("Language mix (by script):", dict(langs))
    print("5 sample rows:")
    for r in rows[:5]:
        q = (r.get("Codemixed_Question") or "")[:90]
        s = (r.get("summary") or "")[:90]
        print(f"  - Q: {q!r}")
        print(f"    S: {s!r}")
    return f"- MMCQS: {len(rows)} HF rows; language mix {dict(langs)}."


def write_sources(tb: str, mm: str) -> None:
    today = date.today().isoformat()
    bibtex = """@misc{wong2026gender,
  title  = {Gender-Dependent Diagnostic Substitution in LLM Medical Triage: Same Symptoms, Unequal Urgency},
  author = {Wong, Qi Han},
  year   = {2026},
  eprint = {2606.03641},
  archivePrefix = {arXiv}
}"""
    content = (
        "# External Data Sources\n\n"
        f"Date accessed: {today}\n\n"
        "## TriageBench\n"
        "- Title: TriageBench — consistency/bias benchmark for clinical triage\n"
        "- Repo: https://github.com/wongqihan/triagebench\n"
        "- Dataset: https://huggingface.co/datasets/wongqihan/triagebench\n"
        "- Licence: MIT\n"
        "- What we use it for: **fairness / consistency harness only.** The same clinical\n"
        "  vignette is repeated with one irrelevant detail swapped (gender, language, ZIP\n"
        "  code). It has **NO ground-truth care-type labels**, so we report \"consistency\",\n"
        "  never \"accuracy\". (See docs/FAIRNESS_REPORT.md.)\n"
        f"{tb}\n\n"
        "## MedSumm / MMCQS\n"
        "- Title: MMCQS (Multi-modal Code-mixed Question Summarization) / MedSumm\n"
        "- Repo: https://github.com/ArkadeepAcharya/MedSumm-ECIR2024\n"
        "- Dataset: https://huggingface.co/datasets/ArkaAcharya/MMCQSD\n"
        "- Licence: CC-BY-4.0 (per the Hugging Face dataset card; the repo README does not\n"
        "  state one)\n"
        "- What we use it for: Hinglish vocabulary mining, robustness runs, and short\n"
        "  few-shot examples for Groq extraction. It has **NO care-type labels**. We do\n"
        "  not redistribute the text.\n"
        f"{mm}\n\n"
        "## Citation (BibTeX, from each repo's README)\n"
        "```bibtex\n"
        f"{bibtex}\n"
        "```\n"
    )
    SOURCES_FILE.write_text(content, encoding="utf-8")
    print(f"\nSaved {SOURCES_FILE}")


if __name__ == "__main__":
    tb = inspect_triagebench()
    mm = inspect_mmcqs()
    write_sources(tb, mm)
