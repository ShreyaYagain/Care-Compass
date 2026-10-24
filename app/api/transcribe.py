import os
import tempfile
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.config import settings
from app.schemas import TranscribeResponse
from app.core.llm import get_groq_client, is_groq_available

router = APIRouter(tags=["Transcription"])
logger = logging.getLogger(__name__)

PROMPT_HINT = "bukhar, khansi, dard, saans, ulti, injection, dressing, checkup, fever, cough"


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: Optional[str] = Form("auto")
):
    """
    Transcribes uploaded audio file (.m4a, .wav, .mp3, .ogg, .webm, .flac)
    Primary: Groq Whisper API (whisper-large-v3-turbo) with medical prompt hint and 5s timeout.
    Fallback: local faster-whisper if available, or HTTP 503.
    """
    lang_hint = None
    if language:
        l_lower = language.lower()
        if "en" in l_lower:
            lang_hint = "en"
        elif "hi" in l_lower or "hinglish" in l_lower:
            lang_hint = "hi"

    contents = await audio.read()
    suffix = os.path.splitext(audio.filename or "")[1] or ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        # 1. Primary: Groq Whisper API
        if is_groq_available():
            client = get_groq_client()
            if client:
                try:
                    with open(tmp_path, "rb") as file_handle:
                        transcription_kwargs = {
                            "file": (os.path.basename(tmp_path), file_handle),
                            "model": settings.GROQ_STT_MODEL,
                            "prompt": PROMPT_HINT,
                            "temperature": 0.0,
                            "response_format": "verbose_json",
                        }
                        if lang_hint:
                            transcription_kwargs["language"] = lang_hint

                        groq_res = client.audio.transcriptions.create(**transcription_kwargs)

                    text = getattr(groq_res, "text", "") or ""
                    detected_language = getattr(groq_res, "language", None) or (lang_hint or "en")
                    return TranscribeResponse(
                        text=text.strip(),
                        language="hi" if "hi" in detected_language.lower() else "en"
                    )
                except Exception as e:
                    logger.warning(f"Groq Whisper transcription failed: {e}. Trying local fallback if available...")

        # 2. Fallback: local faster-whisper
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("small", device="cpu", compute_type="int8")
            segments, info = model.transcribe(tmp_path, language=lang_hint)
            full_text = " ".join([seg.text.strip() for seg in segments]).strip()
            detected_lang = info.language or ("hi" if lang_hint == "hi" else "en")
            return TranscribeResponse(text=full_text, language=detected_lang)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Local faster-whisper fallback failed: {e}")

        # If both fail or unavailable
        raise HTTPException(
            status_code=503,
            detail="Audio transcription service temporarily unavailable. Please type your symptoms."
        )
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
