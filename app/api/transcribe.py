import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException

from app.core.language import detect_script_and_language
from app.core.llm import deepseek_validate_transcript, is_llm_available
from app.schemas import TranscribeResponse

router = APIRouter(tags=["Transcription"])
logger = logging.getLogger(__name__)


def _detect_lang(text: str) -> str:
    lang = detect_script_and_language(text)
    if lang == "hi":
        return "hi"
    if lang == "hinglish":
        return "hinglish"
    return "en"


def _normalise_lang(lang: str) -> str:
    lang = (lang or "").strip().lower()
    return lang if lang in ("hi", "hinglish", "en") else "en"


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    text: str = Form(...),
    language: Optional[str] = Form("auto"),
):
    """
    Validates/normalises a raw on-device speech transcript using DeepSeek.

    The client performs speech recognition on-device (Android SpeechRecognizer)
    and posts the resulting text here; DeepSeek cleans it up for triage.
    """
    raw = (text or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty transcript.")

    if not is_llm_available():
        raise HTTPException(
            status_code=503,
            detail="Transcription service temporarily unavailable. Please type your symptoms.",
        )

    try:
        validated = deepseek_validate_transcript(raw, language or "auto")
        if validated is None or not (validated.text or "").strip():
            raise HTTPException(
                status_code=503,
                detail="Transcription validation failed. Please type your symptoms.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Transcription validation error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Transcription service temporarily unavailable. Please type your symptoms.",
        )

    result_text = validated.text.strip()
    detected = _normalise_lang(validated.language) if validated.language else _detect_lang(result_text)
    return TranscribeResponse(text=result_text, language=detected)
