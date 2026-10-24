import csv
from pathlib import Path
import numpy as np
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report, f1_score, recall_score
from app.core.language import normalise_text

DATA_DIR = Path(__file__).resolve().parent / "data"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def train_models():
    train_file = DATA_DIR / "train.csv"
    val_file = DATA_DIR / "val.csv"

    if not train_file.exists() or not val_file.exists():
        print("Data files missing. Run ml.prepare_data and ml.augment_synthetic first.")
        return

    train_texts, train_labels, train_langs = [], [], []
    with open(train_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            train_texts.append(row["norm_input"] or normalise_text(row["user_input"]))
            train_labels.append(row["care_type"])
            train_langs.append(row.get("language", "English"))

    val_texts, val_labels, val_langs = [], [], []
    with open(val_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            val_texts.append(row["norm_input"] or normalise_text(row["user_input"]))
            val_labels.append(row["care_type"])
            val_langs.append(row.get("language", "English"))

    # Word and char ngrams combined vectorizer
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 3),
        min_df=1,
        sublinear_tf=True,
    )
    X_train = vectorizer.fit_transform(train_texts)
    X_val = vectorizer.transform(val_texts)

    base_clf = LogisticRegression(
        C=2.0,
        class_weight="balanced",
        max_iter=500,
        random_state=42,
    )
    care_clf = CalibratedClassifierCV(estimator=base_clf, cv=3)
    care_clf.fit(X_train, train_labels)

    # Save artifacts
    joblib.dump(vectorizer, ARTIFACTS_DIR / "tfidf_vectorizer.joblib")
    joblib.dump(care_clf, ARTIFACTS_DIR / "triage_care.joblib")

    # Evaluation on unseen validation set
    val_preds = care_clf.predict(X_val)

    macro_f1 = f1_score(val_labels, val_preds, average="macro", zero_division=0)
    classes = sorted(list(set(train_labels + val_labels)))

    print("=" * 65)
    print(" CareCompass Official Model Evaluation Report (Validation Set)")
    print("=" * 65)
    print(f"Overall Validation Macro-F1: {macro_f1:.4f}")
    print("\n--- Per-Class Performance ---")
    report = classification_report(val_labels, val_preds, zero_division=0, output_dict=True)

    print(f"{'Class':<25} {'Precision':<10} {'Recall':<10} {'F1-Score':<10} {'Support':<8}")
    print("-" * 65)
    for cls in classes:
        metrics = report.get(cls, {})
        p = metrics.get("precision", 0.0)
        r = metrics.get("recall", 0.0)
        f = metrics.get("f1-score", 0.0)
        s = metrics.get("support", 0)
        print(f"{cls:<25} {p:<10.3f} {r:<10.3f} {f:<10.3f} {s:<8}")

    emergency_recall = report.get("emergency_112", {}).get("recall", 0.0)
    print("-" * 65)
    print(f"Emergency Recall on 'emergency_112': {emergency_recall:.4f}")

    print("\n--- Per-Language Scores ---")
    val_langs_arr = np.array(val_langs)
    val_labels_arr = np.array(val_labels)
    val_preds_arr = np.array(val_preds)

    for lang in sorted(list(set(val_langs))):
        mask = (val_langs_arr == lang)
        if np.sum(mask) > 0:
            lang_f1 = f1_score(val_labels_arr[mask], val_preds_arr[mask], average="macro", zero_division=0)
            lang_acc = np.mean(val_labels_arr[mask] == val_preds_arr[mask])
            print(f"{lang:<15} Accuracy: {lang_acc:.4f}  |  Macro-F1: {lang_f1:.4f}  (n={np.sum(mask)})")
    print("=" * 65)
    print("Successfully trained and saved artifacts to ml/artifacts/")


if __name__ == "__main__":
    train_models()
