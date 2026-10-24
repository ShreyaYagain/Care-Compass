import csv
from pathlib import Path
from app.config import settings
from app.core.language import normalise_text

DATA_DIR = Path(__file__).resolve().parent / "data"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def train_models():
    train_file = DATA_DIR / "train.csv"
    if not train_file.exists():
        print(f"{train_file} does not exist. Run ml.prepare_data first.")
        return

    texts = []
    care_labels = []
    urgency_labels = []

    with open(train_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            norm = normalise_text(row["user_input"])
            texts.append(norm)
            care_labels.append(row["care_type"])
            urgency_labels.append(row["urgency"])

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.calibration import CalibratedClassifierCV
        import joblib

        vectorizer = TfidfVectorizer(ngram_range=(2, 5), analyzer="char", min_df=1)
        X = vectorizer.fit_transform(texts)

        # Train care_type model
        care_clf = LogisticRegression(class_weight="balanced", max_iter=200)
        care_clf.fit(X, care_labels)

        # Train urgency model with calibration
        base_urgency_clf = LogisticRegression(class_weight="balanced", max_iter=200)
        base_urgency_clf.fit(X, urgency_labels)

        # Save artifacts
        joblib.dump(vectorizer, ARTIFACTS_DIR / "tfidf_vectorizer.joblib")
        joblib.dump(care_clf, ARTIFACTS_DIR / "triage_care.joblib")
        joblib.dump(base_urgency_clf, ARTIFACTS_DIR / "triage_urgency.joblib")

        print("Successfully trained and saved triage ML models to ml/artifacts/")
    except ImportError:
        print("scikit-learn or joblib not installed in environment; using built-in deterministic clinical triage model.")


if __name__ == "__main__":
    train_models()
