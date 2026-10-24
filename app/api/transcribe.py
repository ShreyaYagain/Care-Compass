import os
import tempfile
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.config import settings
from app.schemas import TranscribeResponse
from app.core.language import detect_script_and_language
from app.core.llm import gemini_transcribe, is_gemini_available

router = APIRouter(tags=["Transcription"])
logger = logging.getLogger(__name__)

_MIME_BY_SUFFIX = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
}


def _detect_lang(text: str) -> str:
    lang = detect_script_and_language(text)
    if lang == "hi":
        return "hi"
    if lang == "hinglish":
        return "hinglish"
    return "en"


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: Optional[str] = Form("auto")
):
    """
    Transcribes uploaded audio (.m4a, .wav, .mp3, .ogg, .webm, .flac) to text
    using Gemini's multimodal audio input.
    """
    contents = await audio.read()
    suffix = os.path.splitext(audio.filename or "")[1].lower() or ".wav"
    mime_type = _MIME_BY_SUFFIX.get(suffix, "audio/mpeg")

    if not is_gemini_available():
        raise HTTPException(
            status_code=503,
            detail="Audio transcription service temporarily unavailable. Please type your symptoms."
        )

    try:
        text = gemini_transcribe(contents, mime_type)
        if not text:
            raise HTTPException(
                status_code=503,
                detail="Audio transcription failed. Please type your symptoms."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Transcription error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Audio transcription service temporarily unavailable. Please type your symptoms."
        )

    detected = _detect_lang(text)
    return TranscribeResponse(text=text, language=detected)
