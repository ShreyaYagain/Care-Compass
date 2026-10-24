"""Download the two public resources used to improve and validate CareCompass.

Resources (verified: MIT / CC-BY-4.0, neither gated):
  1. TriageBench  - github.com/wongqihan/triagebench, HF "wongqihan/triagebench"
     A consistency/fairness benchmark (NO care-type labels).
  2. MedSumm/MMCQS - github.com/ArkadeepAcharya/MedSumm-ECIR2024,
     HF "ArkaAcharya/MMCQSD". Code-mixed Hindi-English queries + summaries
     (NO care-type labels).

Downloads are stored under ml/external/raw/ (gitignored). If a dataset requires
login/approval, or the network is unavailable, we skip it with a clear message
and fall back to the repo's bundled sample (dataset_sample.csv).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

TRIAGEBENCH_HF = "wongqihan/triagebench"
MMCQS_HF = "ArkaAcharya/MMCQSD"


def _dataset_to_jsonl(dataset, out_path: Path) -> int:
    rows = list(dataset)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return len(rows)


def fetch_triagebench() -> Path | None:
    out = RAW_DIR / "triagebench_hf.jsonl"
    try:
        from datasets import load_dataset
        ds = load_dataset(TRIAGEBENCH_HF)
        split = "test" if "test" in ds else "train"
        n = _dataset_to_jsonl(ds[split], out)
        print(f"[TriageBench] downloaded {n} rows -> {out}")
        return out
    except Exception as e:
        msg = str(e).lower()
        if "gate" in msg or "login" in msg or "approval" in msg or "401" in msg or "403" in msg:
            print(f"[TriageBench] SKIPPED: requires login/approval ({e}). "
                  f"Using repo vignettes under raw/triagebench/ instead.")
        else:
            print(f"[TriageBench] SKIPPED: download failed ({e}). "
                  f"Using repo vignettes under raw/triagebench/ instead.")
        return None


def fetch_mmcqs() -> Path | None:
    out = RAW_DIR / "mmcqs_hf.jsonl"
    try:
        from datasets import load_dataset
        ds = load_dataset(MMCQS_HF)
        split = "train" if "train" in ds else list(ds.keys())[0]
        n = _dataset_to_jsonl(ds[split], out)
        print(f"[MMCQS] downloaded {n} rows -> {out}")
        return out
    except Exception as e:
        msg = str(e).lower()
        if "gate" in msg or "login" in msg or "approval" in msg or "401" in msg or "403" in msg:
            print(f"[MMCQS] SKIPPED: requires login/approval ({e}). "
                  f"Using repo sample dataset_sample.csv instead.")
        else:
            print(f"[MMCQS] SKIPPED: download failed ({e}). "
                  f"Using repo sample dataset_sample.csv instead.")
        return None


def fallback_mmcqs_sample() -> Path | None:
    """Copy the repo's bundled dataset_sample.csv into raw/ for a stable path."""
    sample = Path(__file__).resolve().parent.parent / "raw" / "MedSumm-ECIR2024" / "dataset_sample.csv"
    if not sample.exists():
        sample = RAW_DIR / "MedSumm-ECIR2024" / "dataset_sample.csv"
    if not sample.exists():
        return None
    out = RAW_DIR / "mmcqs_sample.csv"
    with open(sample, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"[MMCQS] using repo sample ({len(rows)} rows) -> {out}")
    return out


if __name__ == "__main__":
    fetch_triagebench()
    if not fetch_mmcqs():
        fallback_mmcqs_sample()
    print("Done. Raw downloads live in ml/external/raw/ (gitignored).")
