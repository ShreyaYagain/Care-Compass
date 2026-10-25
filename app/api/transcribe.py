import logging
import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.language import detect_script_and_language
from app.core.llm import is_llm_available, validate_transcript
from app.core.stt import groq_transcribe, local_whisper_transcribe, stt_provider
from app.schemas import TranscribeResponse

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


def _normalise_lang(lang: str) -> str:
    lang = (lang or "").strip().lower()
    return lang if lang in ("hi", "hinglish", "en") else "en"


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    text: Optional[str] = Form(None),
    language: Optional[str] = Form("auto"),
    audio: Optional[UploadFile] = File(None),
):
    """
    STT endpoint. Two modes, gated by STT_PROVIDER:

    - android_only (default when no Groq key): the client transcribes on-device
      (SpeechRecognizer) and posts `text`; the LLM validates/normalises it.
    - groq_whisper / local_whisper: the client posts `audio`; the server
      transcribes it with Groq Whisper or a local Whisper model.
    """
    provider = stt_provider()

    # Server-side audio transcription.
    if audio is not None:
        if provider == "android_only":
            raise HTTPException(
                status_code=400,
                detail="Voice input is on-device on this build. Please send the transcript text, not audio.",
            )
        contents = await audio.read()
        if provider == "groq_whisper":
            suffix = os.path.splitext(audio.filename or "")[1].lower() or ".wav"
            mime = _MIME_BY_SUFFIX.get(suffix, "audio/mpeg")
            transcript = groq_transcribe(contents, mime)
        elif provider == "local_whisper":
            transcript = local_whisper_transcribe(contents)
        else:
            transcript = ""
        if not transcript:
            raise HTTPException(
                status_code=503,
                detail="Audio transcription failed. Please type your symptoms.",
            )
        return TranscribeResponse(text=transcript, language=_detect_lang(transcript))

    # On-device transcript validation (android_only / post-processing).
    raw = (text or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty transcript.")

    if not is_llm_available():
        raise HTTPException(
            status_code=503,
            detail="Transcription service temporarily unavailable. Please type your symptoms.",
        )

    try:
        validated = validate_transcript(raw, language or "auto")
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
