import re
import numpy as np
import scipy.sparse as sp
from sklearn.metrics.pairwise import cosine_similarity


def get_top_contributing_terms(vectorizer, classifier, text: str, predicted_class: str, top_k: int = 5) -> list[dict]:
    """
    Computes top contributing words/n-grams for the predicted care type:
    feature_value * coefficient for that class.
    Maps back to readable terms and returns list of {'term': str, 'weight': round(float, 4)}.
    """
    if vectorizer is None or classifier is None:
        return []

    try:
        # Check if classifier is CalibratedClassifierCV or fitted linear model
        if hasattr(classifier, "calibrated_classifiers_") and len(classifier.calibrated_classifiers_) > 0:
            base_estimator = classifier.calibrated_classifiers_[0].estimator
        elif hasattr(classifier, "estimator") and hasattr(classifier.estimator, "coef_"):
            base_estimator = classifier.estimator
        elif hasattr(classifier, "coef_"):
            base_estimator = classifier
        else:
            base_estimator = None

        if base_estimator is None or not hasattr(base_estimator, "coef_"):
            return []

        classes = list(getattr(classifier, "classes_", getattr(base_estimator, "classes_", [])))
        if predicted_class not in classes:
            return []

        class_idx = classes.index(predicted_class)
        coef = base_estimator.coef_[class_idx]
        feature_names = vectorizer.get_feature_names_out()

        # Transform text
        x_vec = vectorizer.transform([text])
        if x_vec.nnz == 0:
            return []

        feature_indices = x_vec.indices
        feature_values = x_vec.data

        contributions = []
        for idx, val in zip(feature_indices, feature_values):
            weight = coef[idx] * val
            if weight > 0:
                contributions.append((feature_names[idx], weight))

        # Sort descending by contribution weight
        contributions.sort(key=lambda item: item[1], reverse=True)

        results = []
        seen_terms = set()
        for term, wt in contributions:
            clean_term = term.strip()
            # Clean up character boundary markers if any
            clean_term = re.sub(r"\s+", " ", clean_term).strip()
            if len(clean_term) >= 2 and clean_term not in seen_terms:
                seen_terms.add(clean_term)
                results.append({"term": clean_term, "weight": round(float(wt), 4)})
            if len(results) >= top_k:
                break

        return results
    except Exception:
        return []


def get_nearest_training_examples(query_rep, train_reps, train_meta: list[dict], top_k: int = 3) -> list[dict]:
    """
    Returns top_k nearest official training examples via cosine similarity:
    Supports both sparse TF-IDF feature matrices and dense embeddings.
    [{'text': str, 'care_type': str, 'similarity': float}]
    """
    if query_rep is None or train_reps is None or len(train_meta) == 0:
        return []

    try:
        if sp.issparse(query_rep) or sp.issparse(train_reps):
            sims = cosine_similarity(query_rep, train_reps).flatten()
        else:
            q = np.asarray(query_rep).reshape(1, -1)
            q_norm = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-10)
            t_norm = train_reps / (np.linalg.norm(train_reps, axis=1, keepdims=True) + 1e-10)
            sims = np.dot(t_norm, q_norm.T).flatten()

        top_indices = np.argsort(-sims)[:top_k]

        nearest = []
        for idx in top_indices:
            meta = train_meta[idx]
            nearest.append({
                "text": meta.get("text", ""),
                "care_type": meta.get("care_type", ""),
                "similarity": round(float(sims[idx]), 3),
            })
        return nearest
    except Exception:
        return []
