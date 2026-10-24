import json
import logging
from typing import Any, Type, TypeVar
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_GROQ_CLIENT = None


def get_groq_client():
    global _GROQ_CLIENT
    if _GROQ_CLIENT is None:
        api_key = settings.GROQ_API_KEY.strip() if settings.GROQ_API_KEY else ""
        if api_key:
            try:
                from groq import Groq
                _GROQ_CLIENT = Groq(api_key=api_key, timeout=settings.LLM_TIMEOUT_S)
            except Exception as e:
                logger.warning(f"Could not initialize Groq client: {e}")
                _GROQ_CLIENT = None
    return _GROQ_CLIENT


def is_groq_available() -> bool:
    return bool(settings.GROQ_API_KEY and settings.GROQ_API_KEY.strip())


def is_gemini_available() -> bool:
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())


def is_llm_available() -> bool:
    return is_groq_available() or is_gemini_available()


def call_gemini_json(prompt: str, system_instruction: str = "") -> dict | None:
    """
    Calls Gemini API with strict JSON schema output. Returns parsed dict or None.
    """
    if not is_gemini_available():
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        if response and response.text:
            return json.loads(response.text)
    except Exception as e:
        logger.warning(f"Gemini call failed or timed out: {e}")

    return None


def groq_json(
    system: str,
    user: str,
    schema: Type[T] | None = None,
    model: str | None = None,
) -> T | dict | None:
    """
    Forces JSON output from Groq LLM, validates with Pydantic schema, retries once on error.
    Fallback chain: Groq -> Gemini (if key exists) -> None (rule/regex layer takes over).
    Never crashes.
    """
    client = get_groq_client()
    model_to_use = model or settings.GROQ_MODEL

    if client:
        # Try Groq with 1 retry
        for attempt in range(2):
            try:
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": user})

                resp = client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                raw_text = resp.choices[0].message.content or ""
                data = json.loads(raw_text)

                if schema is not None:
                    if hasattr(schema, "model_validate"):
                        return schema.model_validate(data)
                    return schema(**data)
                return data
            except Exception as e:
                err_str = str(e)
                # If model not found, try fallback fast model or gpt-oss model
                if "model_not_found" in err_str and model_to_use != "openai/gpt-oss-120b":
                    model_to_use = "openai/gpt-oss-120b"
                    continue
                logger.warning(f"Groq LLM call attempt {attempt + 1} failed: {e}")
                if attempt == 1:
                    break

    # Fallback to Gemini if configured
    if is_gemini_available():
        logger.info("Falling back from Groq to Gemini...")
        g_data = call_gemini_json(prompt=user, system_instruction=system)
        if g_data:
            if schema is not None:
                try:
                    if hasattr(schema, "model_validate"):
                        return schema.model_validate(g_data)
                    return schema(**g_data)
                except Exception as e:
                    logger.warning(f"Gemini output failed schema validation: {e}")
                    return None
            return g_data

    # Return None so downstream rule/regex layer takes over cleanly
    return None
