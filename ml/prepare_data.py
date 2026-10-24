import json
import csv
from pathlib import Path
from sklearn.model_selection import GroupShuffleSplit
from app.core.language import normalise_text

DATA_DIR = Path(__file__).resolve().parent / "data"
OFFICIAL_FILE = DATA_DIR / "official" / "triage_dataset.jsonl"


def prepare_datasets():
    if not OFFICIAL_FILE.exists():
        raise FileNotFoundError(f"{OFFICIAL_FILE} not found!")

    # Remove legacy synthetic files
    old_train = DATA_DIR / "train.csv"
    old_gold = DATA_DIR / "gold.csv"
    if old_train.exists():
        old_train.unlink()
    if old_gold.exists():
        old_gold.unlink()

    records = []
    with open(OFFICIAL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            req = obj.get("request", {})
            resp = obj.get("response", {})

            u_in = req.get("user_input", "")
            norm = normalise_text(u_in)
            care_type = resp.get("care_type")
            urgency = resp.get("urgency")
            follow_up = resp.get("follow_up_question")

            records.append({
                "id": obj.get("id"),
                "user_input": u_in,
                "norm_input": norm,
                "language": obj.get("detected_language", "English"),
                "care_type": care_type if care_type else "follow_up",
                "urgency": urgency if urgency else "",
                "red_flags": ";".join(resp.get("red_flags") or []),
                "follow_up_question": follow_up or "",
                "source": "official_sanocare",
            })

    # GroupShuffleSplit on unique norm_input to ensure identical texts are never in both train & val
    groups = [r["norm_input"] for r in records]
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, val_idx = next(gss.split(records, groups=groups))

    train_records = [records[i] for i in train_idx]
    val_records = [records[i] for i in val_idx]

    fieldnames = [
        "id", "user_input", "norm_input", "language", "care_type",
        "urgency", "red_flags", "follow_up_question", "source"
    ]

    train_file = DATA_DIR / "train.csv"
    val_file = DATA_DIR / "val.csv"

    with open(train_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(train_records)

    with open(val_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(val_records)

    print(f"Prepared datasets: Train={len(train_records)}, Val={len(val_records)}")
    print(f"Unique texts in Train: {len(set(r['norm_input'] for r in train_records))}")
    print(f"Unique texts in Val: {len(set(r['norm_input'] for r in val_records))}")


if __name__ == "__main__":
    prepare_datasets()
