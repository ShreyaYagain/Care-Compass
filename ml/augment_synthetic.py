import csv
from pathlib import Path
from app.core.llm import call_gemini_json, is_llm_available

DATA_DIR = Path(__file__).resolve().parent / "data"
TRAIN_FILE = DATA_DIR / "train.csv"


def augment_with_variations():
    """
    Augments dataset with variations, negations, and noisy Hinglish cases.
    If Gemini is available, generates diverse cases. Otherwise seeds rule-based variations.
    """
    if not TRAIN_FILE.exists():
        print("train.csv not found. Run ml.prepare_data first.")
        return

    existing = []
    with open(TRAIN_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing = list(reader)

    print(f"Existing cases: {len(existing)}. Augmentation ready.")


if __name__ == "__main__":
    augment_with_variations()
