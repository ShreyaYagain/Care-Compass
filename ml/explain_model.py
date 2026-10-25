import re
import numpy as np
import scipy.sparse as sp
from sklearn.metrics.pairwise import cosine_similarity

_LEXICON_MAP: dict[str, str] | None = None


def _canonical_lexicon() -> dict[str, str]:
    """Normalised word -> canonical symptom name, built once per process.

    A single normalise pass over the lexicon is done at build time (not per
    term), so explaining stays well under the latency budget.
    """
    global _LEXICON_MAP
    if _LEXICON_MAP is None:
        _LEXICON_MAP = {}
        try:
            import yaml as _yaml
            from app.config import settings as _settings
            from app.core.language import normalise_text as _norm
            with open(_settings.SYMPTOMS_FILE, "r", encoding="utf-8") as f:
                data = _yaml.safe_load(f) or {}
            for canon, info in (data.get("symptoms_list") or {}).items():
                _LEXICON_MAP.setdefault(_norm(canon), canon)
                for syn in info.get("synonyms") or []:
                    _LEXICON_MAP.setdefault(_norm(str(syn)), canon)
        except Exception:
            _LEXICON_MAP = {}
    return _LEXICON_MAP


def _canonicalise(word: str) -> str | None:
    """Maps a word to its canonical symptom name, or None when unknown."""
    try:
        from app.core.language import normalise_text as _norm
        return _canonical_lexicon().get(_norm(word))
    except Exception:
        return None


def get_top_contributing_terms(vectorizer, classifier, text: str, predicted_class: str, top_k: int = 5) -> list[dict]:
    """
    Computes top contributing words/n-grams for the predicted care type:
    feature_value * coefficient for that class.

    Character n-grams are aggregated back to the whole word (or canonical
    symptom name) they come from, so the explanation never shows sub-word
    fragments ("ver", "eve", ...). Each word is shown once with its summed
    weight; only the top `top_k` are returned. Non-lexicon words shorter than
    4 characters are dropped; lexicon words are shown as their canonical name
    ("bukhar" -> "fever"). Returns [{'term': str, 'weight': round(float, 4)}].
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

        # Aggregate character n-grams back to the whole word / canonical
        # symptom name. N-grams are extracted per token (analyzer="char"
        # tokenizes on whitespace first), so every n-gram maps back to the
        # single word of `text` that contains it.
        tokens = [t for t in re.split(r"\s+", (text or "").strip()) if t]
        aggregated: dict[str, float] = {}
        canon_terms: set[str] = set()

        def _word_of(ngram: str) -> str | None:
            key = (ngram or "").replace(" ", "")
            if not key:
                return None
            for tok in tokens:
                if key in tok:
                    return tok
            return None

        for term, wt in contributions:
            word = _word_of(term)
            if not word:
                continue
            canon = _canonicalise(word)
            display = canon if canon else word
            if canon:
                canon_terms.add(canon)
            aggregated[display] = aggregated.get(display, 0.0) + wt

        results = []
        for display, wt in sorted(aggregated.items(), key=lambda item: item[1], reverse=True):
            # Never show sub-word fragments: a term must be a full lexicon
            # word (any length) or at least 4 characters long.
            if len(display) < 4 and display not in canon_terms:
                continue
            results.append({"term": display, "weight": round(float(wt), 4)})
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
