import json
import logging
import re
from typing import Any, Type, TypeVar

import requests
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# DeepSeek (primary LLM — OpenAI-compatible chat completions)
# ---------------------------------------------------------------------------

def is_deepseek_available() -> bool:
    return bool(settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY.strip())


def is_llm_available() -> bool:
    return is_deepseek_available()


def _deepseek_endpoint() -> str:
    return settings.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"


def deepseek_chat(
    system: str,
    user: str,
    model: str | None = None,
    timeout: float | None = None,
    json_mode: bool = True,
    temperature: float = 0.0,
) -> str | None:
    """Single DeepSeek chat-completions call. Returns the assistant text, or
    None on any error so the rule/regex layer takes over cleanly."""
    if not is_deepseek_available():
        return None

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    payload: dict[str, Any] = {
        "model": model or settings.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(
            _deepseek_endpoint(),
            headers=headers,
            json=payload,
            timeout=timeout or settings.LLM_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return content.strip()
    except Exception as e:
        logger.warning(f"DeepSeek call failed: {e}")
        return None


def _parse_json(text: str) -> Any:
    """Best-effort JSON parse, stripping code fences and surrounding prose."""
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


def llm_json(
    system: str,
    user: str,
    schema: Type[T] | None = None,
    model: str | None = None,
    timeout: float | None = None,
    retries: int = 1,
) -> T | dict | None:
    """Forces JSON output from DeepSeek, validates with a Pydantic schema.
    `retries` = extra attempts after the first one (default 1). Never crashes;
    returns None so the rule/regex layer takes over cleanly."""
    for attempt in range(retries + 1):
        raw = deepseek_chat(system=system, user=user, model=model, timeout=timeout, json_mode=True)
        if raw is None:
            logger.warning(f"DeepSeek LLM call attempt {attempt + 1} failed")
            continue

        data = _parse_json(raw)
        if data is None:
            logger.warning(f"DeepSeek output was not valid JSON (attempt {attempt + 1})")
            continue

        if schema is not None:
            try:
                if hasattr(schema, "model_validate"):
                    return schema.model_validate(data)
                return schema(**data)
            except Exception as e:
                logger.warning(f"DeepSeek output failed schema validation: {e}")
                return None
        return data

    return None


class TranscriptValidation(BaseModel):
    text: str = ""
    language: str = "en"


def deepseek_validate_transcript(text: str, language_hint: str = "auto") -> TranscriptValidation | None:
    """Validates/normalises a raw on-device speech transcript with DeepSeek.

    Fixes obvious recognition mistakes and drops filler/stray punctuation while
    preserving the patient's actual words; never adds symptoms or facts that are
    not present. Returns the cleaned transcript + detected language, or None.
    """
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
