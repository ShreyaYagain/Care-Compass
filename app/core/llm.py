import json
import logging
from typing import Any, Type, TypeVar
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_GEMINI_CLIENTS: dict[float, Any] = {}


def _get_gemini_client(timeout: float | None = None) -> Any:
    """Returns a cached Gemini client. `timeout` (seconds) creates/returns a
    dedicated client so callers can run on their own time budget. Gemini
    requires a minimum deadline of 10s, so shorter budgets are clamped up."""
    timeout = timeout or settings.LLM_TIMEOUT_S
    client = _GEMINI_CLIENTS.get(timeout)
    if client is None:
        try:
            from google import genai
            from google.genai import types
            timeout_ms = max(int(timeout * 1000), 10_000)
            client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=timeout_ms),
            )
        except Exception as e:
            logger.warning(f"Could not initialise Gemini client: {e}")
            client = None
        _GEMINI_CLIENTS[timeout] = client
    return client


def is_gemini_available() -> bool:
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())


def is_llm_available() -> bool:
    return is_gemini_available()


def call_gemini_json(
    prompt: str,
    system_instruction: str = "",
    model: str | None = None,
    timeout: float | None = None,
) -> dict | None:
    """
    Calls Gemini with strict JSON output. Returns parsed dict or None.
    """
    if not is_gemini_available():
        return None

    try:
        from google.genai import types

        client = _get_gemini_client(timeout)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = client.models.generate_content(
            model=model or settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        if response and response.text:
            return json.loads(response.text)
    except Exception as e:
        logger.warning(f"Gemini call failed or timed out: {e}")

    return None


def llm_json(
    system: str,
    user: str,
    schema: Type[T] | None = None,
    model: str | None = None,
    timeout: float | None = None,
    retries: int = 1,
) -> T | dict | None:
    """
    Forces JSON output from Gemini, validates with a Pydantic schema.
    `retries` = extra attempts after the first one (default 1). Never crashes;
    returns None so the rule/regex layer takes over cleanly.
    """
    for attempt in range(retries + 1):
        data = call_gemini_json(
            prompt=user,
            system_instruction=system,
            model=model or settings.GEMINI_MODEL,
            timeout=timeout,
        )
        if data is None:
            logger.warning(f"Gemini LLM call attempt {attempt + 1} failed")
            continue

        if schema is not None:
            try:
                if hasattr(schema, "model_validate"):
                    return schema.model_validate(data)
                return schema(**data)
            except Exception as e:
                logger.warning(f"Gemini output failed schema validation: {e}")
                return None
        return data

    return None


def gemini_transcribe(audio_bytes: bytes, mime_type: str) -> str:
    """
    Transcribes speech to text with Gemini (multimodal audio input).
    Returns the transcription text, or "" on failure.
    """
    if not is_gemini_available():
        return ""

    try:
        from google.genai import types

        client = _get_gemini_client(timeout=settings.LLM_TIMEOUT_S)
        response = client.models.generate_content(
            model=settings.GEMINI_STT_MODEL,
            contents=[
                "Transcribe the speech in this audio verbatim. Output only the transcription text, with no preamble.",
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.warning(f"Gemini transcription failed: {e}")
        return ""
