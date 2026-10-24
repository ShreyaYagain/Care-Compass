import json
import logging
from app.config import settings

logger = logging.getLogger(__name__)


def is_llm_available() -> bool:
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())


def call_gemini_json(prompt: str, system_instruction: str = "") -> dict | None:
    """
    Calls Gemini API with strict JSON schema output and short timeout.
    Returns parsed dictionary or None on timeout/failure.
    """
    if not is_llm_available():
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
