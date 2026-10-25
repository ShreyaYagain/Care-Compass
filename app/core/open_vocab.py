"""Open-vocabulary symptom resolver (Part 2).

After the lexicon (rule_based_extract + fuzzy matching) finds nothing, the
intake resolver tries, in order, and stops at the first step that yields a
validated symptom:

  1. Lexicon + fuzzy matching (in app/core/intake.py)
  2. Offline embedding match (multilingual-e5-small -> nearest lexicon symptom)
  3. DeepSeek mapper (strict JSON, symptom IDs from symptoms.yaml only)
  4. Buttons (the pipeline's "What is bothering you?" clue buttons)

Every miss is logged to ml/results/lexicon_misses.jsonl (masked, no session id)
and resolver counts + lexicon-miss rate are exposed via /health.
"""
from __future__ import annotations

import difflib
import json
import logging
import threading
from pathlib import Path
from typing import Optional

from app.config import settings, ML_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fuzzy token matching (similarity >= 0.88 for tokens of 6+ chars)
# ---------------------------------------------------------------------------

_FUZZY_MIN_LEN = 6
_FUZZY_THRESHOLD = 0.88


def token_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def fuzzy_match_token(token: str, candidates: list[str], threshold: float = _FUZZY_THRESHOLD) -> Optional[str]:
    """Returns the candidate most similar to `token` when it clears `threshold`,
    else None. Only tokens of 6+ chars are fuzzy-matched (short tokens are
    rejected to avoid false positives on function words)."""
    token = (token or "").strip().lower()
    if len(token) < _FUZZY_MIN_LEN:
        return None
    best: Optional[tuple[float, str]] = None
    for c in candidates:
        c = (c or "").strip().lower()
        if len(c) < _FUZZY_MIN_LEN:
            continue
        s = token_similarity(token, c)
        if s >= threshold and (best is None or s > best[0]):
            best = (s, c)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Offline embedding match (multilingual-e5-small)
# ---------------------------------------------------------------------------

_EMBEDDER = None
_EMBEDDER_LOCK = threading.Lock()
_SYMPTOM_EMB_ARTIFACT = settings.ARTIFACTS_DIR / "symptom_embeddings.joblib"
# High-precision threshold. Calibrated on the training split only (see
# ml/calibrate_embedding_threshold.py): the argmax symptom is directionally
# correct 90% of the time (47/52), but the cosine scores are compressed — the
# correct-match median is 0.856 while pure noise ("blah blah") reaches 0.855, so
# there is no clean threshold. We keep it conservative (never maps noise) and
# rely on the DeepSeek mapper + buttons as the primary open-vocabulary resolvers.
_EMBEDDING_THRESHOLD = 0.90


def _load_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        with _EMBEDDER_LOCK:
            if _EMBEDDER is None:
                from sentence_transformers import SentenceTransformer
                _EMBEDDER = SentenceTransformer("intfloat/multilingual-e5-small")
    return _EMBEDDER


def _lexicon_entries() -> list[tuple[str, str]]:
    """[(label, canonical_symptom)] for every symptom name + synonym, for the
    embedding index. Service-request symptoms (nursing/lab/teleconsult) are
    skipped so the embedding matcher only maps to real complaints."""
    import yaml
    if not settings.SYMPTOMS_FILE.exists():
        return []
    try:
        data = yaml.safe_load(settings.SYMPTOMS_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    skip = {"nursing_procedure", "lab_test", "teleconsultation_query", "chest_pain", "breathlessness"}
    entries: list[tuple[str, str]] = []
    for canon, info in (data.get("symptoms_list") or {}).items():
        if canon in skip:
            continue
        entries.append((canon.replace("_", " "), canon))
        for syn in info.get("synonyms", []) or []:
            entries.append((syn, canon))
    return entries


def _symptom_index():
    """Loads or lazily builds the (labels, canonical, embeddings) index."""
    import joblib
    if _SYMPTOM_EMB_ARTIFACT.exists():
        try:
            idx = joblib.load(_SYMPTOM_EMB_ARTIFACT)
            return idx["labels"], idx["canonical"], idx["embs"]
        except Exception as e:
            logger.warning(f"Could not load symptom embeddings: {e}")
    entries = _lexicon_entries()
    if not entries:
        return [], [], None
    labels = [e[0] for e in entries]
    canonical = [e[1] for e in entries]
    try:
        model = _load_embedder()
        embs = model.encode(
            ["passage: " + l for l in labels],
            show_progress_bar=False, batch_size=32, normalize_embeddings=True,
        )
    except Exception as e:
        logger.warning(f"Could not build symptom embeddings: {e}")
        return labels, canonical, None
    _SYMPTOM_EMB_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    try:
        joblib.dump({"labels": labels, "canonical": canonical, "embs": embs}, _SYMPTOM_EMB_ARTIFACT)
    except Exception as e:
        logger.warning(f"Could not cache symptom embeddings: {e}")
    return labels, canonical, embs


def embedding_match(text: str) -> Optional[tuple[str, float]]:
    """Returns (canonical_symptom, similarity) or None when the embedder is
    unavailable or nothing clears the threshold. Never raises."""
    if not text or not text.strip():
        return None
    labels, canonical, embs = _symptom_index()
    if embs is None:
        return None
    try:
        import numpy as np
        model = _load_embedder()
        q = model.encode(["query: " + text.strip()], show_progress_bar=False, normalize_embeddings=True)
        sims = np.asarray(embs) @ q[0]
        best = int(np.argmax(sims))
        score = float(sims[best])
        if score >= _EMBEDDING_THRESHOLD:
            return canonical[best], score
    except Exception as e:
        logger.warning(f"Embedding match failed: {e}")
    return None


# ---------------------------------------------------------------------------
# DeepSeek mapper (strict enum, evidence_quote + other_text)
# ---------------------------------------------------------------------------

_MAPPER_SYSTEM = (
    "You are a clinical symptom mapper for an Indian home-care app.\n"
    "Map the patient message to AT MOST ONE symptom from the closed list below.\n"
    "CLOSED SYMPTOM LIST (use exactly one of these ids, nothing else):\n"
    "{symptom_ids}\n"
    "Rules:\n"
    "- Choose a symptom ONLY if it is genuinely present in the message.\n"
    "- If nothing in the list fits, set symptom to null.\n"
    "- evidence_quote must be an EXACT substring of the message that supports the choice.\n"
    "- Put any remaining unmapped words into other_text.\n"
    "- You NEVER choose a care type, an urgency, or a red flag.\n"
    "Return valid JSON: {{\"symptom\": <id|null>, \"evidence_quote\": \"...\", \"other_text\": \"...\"}}"
)


def _symptom_ids() -> list[str]:
    import yaml
    try:
        data = yaml.safe_load(settings.SYMPTOMS_FILE.read_text(encoding="utf-8")) or {}
        ids = list((data.get("symptoms_list") or {}).keys())
        # Red-flag and service symptoms are never chosen by the symptom mapper;
        # red flags are handled by the dedicated rules + screen layers.
        return [i for i in ids if i not in {"chest_pain", "breathlessness", "nursing_procedure", "lab_test", "teleconsultation_query"}]
    except Exception:
        return []


def llm_map_symptom(text: str) -> Optional[dict]:
    """Strict-enum DeepSeek symptom mapper. Returns
    {"symptom", "evidence_quote", "other_text"} or None when unavailable."""
    from pydantic import BaseModel
    from app.core.llm import llm_json, is_llm_available, llm_fast_model, llm_fast_effort
    from app.core.language import normalise_text

    if not is_llm_available():
        return None
    ids = _symptom_ids()
    if not ids:
        return None

    class SymptomMap(BaseModel):
        symptom: Optional[str] = None
        evidence_quote: str = ""
        other_text: str = ""

    system = _MAPPER_SYSTEM.format(symptom_ids=", ".join(ids))
    try:
        out = llm_json(system=system, user=f"Patient message: \"{text}\"", schema=SymptomMap,
                       model=llm_fast_model(), reasoning_effort=llm_fast_effort(),
                       max_tokens=256)
    except Exception as e:
        logger.warning(f"DeepSeek symptom mapper failed: {e}")
        return None
    if out is None:
        return None
    symptom = (out.symptom or "").strip()
    if symptom not in ids:
        return {"symptom": None, "evidence_quote": "", "other_text": out.other_text or ""}
    # Validate the evidence quote is a real substring of the message.
    quote = (out.evidence_quote or "").strip()
    if quote and (normalise_text(quote) in normalise_text(text) or quote in text):
        return {"symptom": symptom, "evidence_quote": quote, "other_text": out.other_text or ""}
    return {"symptom": symptom, "evidence_quote": "", "other_text": out.other_text or ""}


# ---------------------------------------------------------------------------
# Miss log + resolver counters (exposed via /health)
# ---------------------------------------------------------------------------

_MISS_LOG = ML_DIR / "results" / "lexicon_misses.jsonl"
_LOCK = threading.Lock()
_COUNTS = {"lexicon": 0, "embedding": 0, "llm": 0, "buttons": 0}
_LEXICON_MISSES = 0
_TOTAL = 0


def record_resolution(source: str, lexicon_miss: bool, text: str = "") -> None:
    """Increments the resolver counters and, when the lexicon missed, appends a
    masked record (no session id) to the miss log."""
    global _LEXICON_MISSES, _TOTAL
    with _LOCK:
        _TOTAL += 1
        if source in _COUNTS:
            _COUNTS[source] += 1
        if lexicon_miss:
            _LEXICON_MISSES += 1
            try:
                _MISS_LOG.parent.mkdir(parents=True, exist_ok=True)
                rec = {"text": _mask(text), "resolved_by": source}
                with open(_MISS_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"Could not write miss log: {e}")


def _mask(text: str) -> str:
    """PII mask for the miss log (phone + email); no session id is ever stored."""
    import re
    if not text:
        return text
    t = re.sub(r"(?:\+?91[\s-]?)?[6-9]\d{9}\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", "[PHONE]", text)
    return re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", t)


def resolver_counts() -> dict:
    with _LOCK:
        return dict(_COUNTS)


def lexicon_miss_rate() -> float:
    with _LOCK:
        if _TOTAL == 0:
            return 0.0
        return round(_LEXICON_MISSES / _TOTAL, 4)


def reset_counters() -> None:
    global _LEXICON_MISSES, _TOTAL
    with _LOCK:
        for k in _COUNTS:
            _COUNTS[k] = 0
        _LEXICON_MISSES = 0
        _TOTAL = 0
