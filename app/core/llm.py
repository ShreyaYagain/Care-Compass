"""Provider-agnostic LLM client (OpenAI-compatible chat completions).

Configured via:
  LLM_PROVIDER   = deepseek | groq        (default deepseek)
  LLM_BASE_URL                            (empty -> provider default)
  LLM_MODEL / LLM_FAST_MODEL
  DEEPSEEK_API_KEY / GROQ_API_KEY         (read per provider)

Every call uses JSON mode + temperature 0. Strict-JSON schema validation and the
evidence-quote substring checks live in the callers (semantic_screen,
second_opinion, intake) and are unchanged.
"""
import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Type, TypeVar

import requests
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Disk cache for LLM responses (evaluation re-runs). Keyed by
# (provider, model, prompt version, exact text). Kept out of git.
# ---------------------------------------------------------------------------

_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "ml" / "results" / "llm_cache.jsonl"
_CACHE: dict[str, str] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LOADED = False


def _load_cache() -> None:
    global _CACHE_LOADED
    if _CACHE_LOADED:
        return
    _CACHE_LOADED = True
    try:
        if _CACHE_PATH.exists():
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        _CACHE[rec["key"]] = rec["content"]
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Could not load LLM cache: {e}")


def _cache_key(system: str, user: str, model: str, schema: Type[T] | None) -> str:
    prompt_id = hashlib.sha1((system + "|" + (schema.__name__ if schema else "none")).encode()).hexdigest()[:16]
    text_id = hashlib.sha1((user or "").encode()).hexdigest()[:16]
    return f"{llm_provider()}|{model}|{prompt_id}|{text_id}"


def _read_cache(key: str) -> str | None:
    _load_cache()
    with _CACHE_LOCK:
        return _CACHE.get(key)


def _write_cache(key: str, content: str) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = content
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "content": content}) + "\n")
    except Exception as e:
        logger.warning(f"Could not write LLM cache: {e}")


_PROVIDER_DEFAULT_BASE = {
    "deepseek": "https://api.deepseek.com",
    "groq": "https://api.groq.com/openai/v1",
}


def llm_provider() -> str:
    p = (settings.LLM_PROVIDER or "deepseek").strip().lower()
    return p if p in ("deepseek", "groq") else "deepseek"


def _api_key() -> str:
    if llm_provider() == "groq":
        return (settings.GROQ_API_KEY or "").strip()
    return (settings.DEEPSEEK_API_KEY or "").strip()


def _base_url() -> str:
    if settings.LLM_BASE_URL and settings.LLM_BASE_URL.strip():
        return settings.LLM_BASE_URL.strip()
    if llm_provider() == "deepseek" and settings.DEEPSEEK_BASE_URL:
        return settings.DEEPSEEK_BASE_URL
    return _PROVIDER_DEFAULT_BASE[llm_provider()]


def _endpoint(path: str = "/chat/completions") -> str:
    return _base_url().rstrip("/") + path


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


def is_llm_available() -> bool:
    return bool(_api_key())


def is_deepseek_available() -> bool:  # backward-compat alias
    return llm_provider() == "deepseek" and is_llm_available()


def llm_model() -> str:
    model = (settings.LLM_MODEL or "").strip()
    if not model and llm_provider() == "deepseek":
        model = (settings.DEEPSEEK_MODEL or "").strip()
    return model or "deepseek-chat"


def llm_fast_model() -> str:
    return (settings.LLM_FAST_MODEL or "").strip() or llm_model()


_FAILURE_STATE = {"consecutive": 0, "total": 0, "last_error": None}
_FAILURE_LOCK = threading.Lock()


def consecutive_llm_failures() -> int:
    """Number of consecutive failed/timed-out provider calls (for the eval
    harness's stop-and-report rule)."""
    with _FAILURE_LOCK:
        return _FAILURE_STATE["consecutive"]


def last_llm_error() -> str | None:
    with _FAILURE_LOCK:
        return _FAILURE_STATE["last_error"]


def llm_fallback_count() -> int:
    """Total provider failures since process start (for /health)."""
    with _FAILURE_LOCK:
        return _FAILURE_STATE["total"]


def _record_failure(msg: str) -> None:
    with _FAILURE_LOCK:
        _FAILURE_STATE["consecutive"] += 1
        _FAILURE_STATE["total"] += 1
        _FAILURE_STATE["last_error"] = msg


def _record_success() -> None:
    with _FAILURE_LOCK:
        _FAILURE_STATE["consecutive"] = 0


def _chat_completion(
    system: str,
    user: str,
    model: str | None = None,
    timeout: float | None = None,
    json_mode: bool = True,
    temperature: float = 0.0,
) -> tuple[str | None, int]:
    """Single chat-completions call. Returns (content_or_None, http_status)."""
    if not is_llm_available():
        return None, 0
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    payload: dict[str, Any] = {
        "model": model or llm_model(),
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        resp = requests.post(
            _endpoint(), headers=_headers(), json=payload,
            timeout=timeout or settings.LLM_TIMEOUT_S,
        )
        if resp.status_code >= 400:
            logger.warning(f"LLM call HTTP {resp.status_code}: {resp.text[:200]}")
            _record_failure(f"HTTP {resp.status_code}")
            return None, resp.status_code
        data = resp.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        _record_success()
        return content.strip(), resp.status_code
    except requests.exceptions.Timeout:
        logger.warning("LLM call timed out")
        _record_failure("timeout")
        return None, 408
    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        _record_failure(f"{type(e).__name__}: {e}")
        return None, 0


def llm_chat(
    system: str,
    user: str,
    model: str | None = None,
    timeout: float | None = None,
    json_mode: bool = True,
    temperature: float = 0.0,
) -> str | None:
    content, _ = _chat_completion(system, user, model, timeout, json_mode, temperature)
    return content


deepseek_chat = llm_chat  # backward-compat alias


_RETRYABLE_STATUS = {429, 500, 502, 503, 504, 408}


def _parse_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except Exception:
                pass
    return None


def _schema_result(data: Any, schema: Type[T] | None) -> T | dict | None:
    if schema is None:
        return data
    try:
        if hasattr(schema, "model_validate"):
            return schema.model_validate(data)
        return schema(**data)
    except Exception as e:
        logger.warning(f"LLM output failed schema validation: {e}")
        return None


def llm_json(
    system: str,
    user: str,
    schema: Type[T] | None = None,
    model: str | None = None,
    timeout: float | None = None,
    retries: int = 1,
) -> T | dict | None:
    """JSON-mode call with strict Pydantic validation, backed by a disk cache.
    `retries` extra attempts are made ONLY on 429 / 5xx / timeout."""
    model_name = model or llm_model()
    key = _cache_key(system, user, model_name, schema)
    cached = _read_cache(key)
    if cached is not None:
        data = _parse_json(cached)
        if data is not None:
            return _schema_result(data, schema)

    for attempt in range(retries + 1):
        raw, status = _chat_completion(system, user, model_name, timeout, True)
        if raw is None:
            if status not in _RETRYABLE_STATUS or attempt >= retries:
                return None
            logger.warning(f"LLM retryable failure ({status}), retrying")
            continue
        _write_cache(key, raw)
        data = _parse_json(raw)
        if data is None:
            logger.warning("LLM output was not valid JSON")
            continue
        return _schema_result(data, schema)
    return None


def list_models(timeout: float = 4.0) -> tuple[str, list[str] | None]:
    """Returns ("ok"|"401"|"429"|"5xx"|"timeout"|"error", [model ids] or None)."""
    if not is_llm_available():
        return "no_key", None
    try:
        resp = requests.get(_endpoint("/models"), headers=_headers(), timeout=timeout)
        if resp.status_code == 401:
            return "401", None
        if resp.status_code == 429:
            return "429", None
        if resp.status_code >= 500:
            return "5xx", None
        if resp.status_code >= 400:
            return "error", None
        data = resp.json()
        return "ok", [m.get("id", "") for m in data.get("data", [])]
    except requests.exceptions.Timeout:
        return "timeout", None
    except Exception as e:
        logger.warning(f"list_models failed: {e}")
        return "error", None


_SELF_TEST_CACHE: dict[str, Any] = {"result": None, "ts": 0.0}


def self_test(timeout: float = 4.0, force: bool = False, ttl: float = 60.0) -> dict:
    """Startup self-test: list models, check the configured names exist, make
    one tiny JSON call. Returns a status dict (never raises). Cached for `ttl`
    seconds so /health does not re-hit the provider on every poll."""
    now = __import__("time").time()
    if not force and _SELF_TEST_CACHE["result"] is not None and (now - _SELF_TEST_CACHE["ts"]) < ttl:
        return _SELF_TEST_CACHE["result"]

    result = {
        "provider": llm_provider(),
        "model": llm_model(),
        "fast_model": llm_fast_model(),
        "available": False,
        "status": "ok",
    }
    if not is_llm_available():
        result["status"] = "no_key"
        _SELF_TEST_CACHE["result"] = result
        _SELF_TEST_CACHE["ts"] = now
        return result
    status, models = list_models(timeout=timeout)
    if status != "ok":
        result["status"] = status
        _SELF_TEST_CACHE["result"] = result
        _SELF_TEST_CACHE["ts"] = now
        return result
    result["models"] = models or []
    if llm_model() not in (models or []):
        result["status"] = "model_not_found"
        _SELF_TEST_CACHE["result"] = result
        _SELF_TEST_CACHE["ts"] = now
        return result
    if llm_fast_model() not in (models or []):
        result["status"] = "model_not_found"
        _SELF_TEST_CACHE["result"] = result
        _SELF_TEST_CACHE["ts"] = now
        return result
    # one tiny JSON call
    out = llm_json(system="", user='Reply with JSON: {"ping": 1}', timeout=timeout, retries=0)
    if out is None:
        result["status"] = "error"
        _SELF_TEST_CACHE["result"] = result
        _SELF_TEST_CACHE["ts"] = now
        return result
    result["available"] = True
    _SELF_TEST_CACHE["result"] = result
    _SELF_TEST_CACHE["ts"] = now
    return result


class TranscriptValidation(BaseModel):
    text: str = ""
    language: str = "en"


def validate_transcript(text: str, language_hint: str = "auto") -> TranscriptValidation | None:
    """Validates/normalises a raw on-device speech transcript with the LLM."""
    if not text or not text.strip():
        return None
    system = (
        "You clean up noisy speech-to-text transcripts for an Indian home-care app. "
        "Fix obvious speech-recognition mistakes, drop filler words (um, uh, hmm) and stray "
        "punctuation, but keep the patient's actual words and meaning. Never add symptoms or "
        "facts that are not present in the transcript. Detect the language and return JSON: "
        "{\"text\": \"...\", \"language\": \"en|hi|hinglish\"}."
    )
    user = f"Transcript: \"{text.strip()}\"\nLanguage hint: {language_hint or 'auto'}"
    return llm_json(system=system, user=user, schema=TranscriptValidation)


deepseek_validate_transcript = validate_transcript  # backward-compat alias
