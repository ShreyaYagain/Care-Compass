"""Merge only the rows marked approved=yes from hinglish_candidates.csv into
app/data/hinglish_norm.json. Never auto-merges unreviewed rows.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

CANDIDATES = Path(__file__).resolve().parent / "hinglish_candidates.csv"
NORM_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "data" / "hinglish_norm.json"


def main() -> None:
    if not CANDIDATES.exists():
        print(f"No candidate file at {CANDIDATES}")
        return

    norm: dict[str, str] = json.loads(NORM_FILE.read_text(encoding="utf-8"))
    added = 0
    with open(CANDIDATES, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("approved") or "").strip().lower() == "yes":
                variant = (row.get("variant") or "").strip()
                canon = (row.get("suggested_canonical") or "").strip()
                if variant and canon and variant not in norm:
                    norm[variant] = canon
                    added += 1

    # Keep stable ordering: phrases (with spaces) first, then words.
    items = sorted(norm.items(), key=lambda kv: (0 if " " in kv[0] else 1, kv[0]))
    NORM_FILE.write_text(
        json.dumps(dict(items), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Merged {added} approved variants into {NORM_FILE} (total {len(norm)} entries).")


if __name__ == "__main__":
    main()
