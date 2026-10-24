import csv
from pathlib import Path
from app.schemas import TriageRequest, Location
from app.core.pipeline import run_triage_pipeline

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = Path(__file__).resolve().parent / "predictions.csv"


def generate_predictions():
    test_file = DATA_DIR / "gold.csv"
    if not test_file.exists():
        test_file = DATA_DIR / "train.csv"

    rows = []
    with open(test_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    predictions = []
    for r in rows:
        req = TriageRequest(
            user_input=r["user_input"],
            language=r.get("language", "auto"),
            location=Location(lat=28.54, lng=77.27),
            conversation_history=[],
        )
        resp = run_triage_pipeline(req)
        predictions.append({
            "id": r["id"],
            "care_type": resp.care_type or "paramedic_home_visit",
            "urgency": resp.urgency or "same_day",
            "red_flags": ";".join(resp.red_flags) if resp.red_flags else "",
        })

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "care_type", "urgency", "red_flags"])
        writer.writeheader()
        for p in predictions:
            writer.writerow(p)

    print(f"Generated {len(predictions)} predictions to {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_predictions()
