"""Speech-to-text provider selection.

STT_PROVIDER = groq_whisper | local_whisper | android_only.

Default resolution: groq_whisper only when a Groq key is present, otherwise
android_only (on-device SpeechRecognizer, with the transcript validated by the
LLM via /transcribe).
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def stt_provider() -> str:
    p = (settings.STT_PROVIDER or "").strip().lower()
    if p in ("groq_whisper", "local_whisper", "android_only"):
        return p
    return "groq_whisper" if (settings.GROQ_API_KEY or "").strip() else "android_only"


def groq_whisper_available() -> bool:
    return bool((settings.GROQ_API_KEY or "").strip())


def groq_transcribe(audio_bytes: bytes, mime_type: str) -> str:
    """Server-side STT via Groq Whisper. Returns transcript text or ''."""
    if not groq_whisper_available():
        return ""
    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY.strip()}"},
            files={"file": ("audio", audio_bytes, mime_type)},
            data={"model": "whisper-large-v3-turbo"},
            timeout=settings.LLM_TIMEOUT_S,
        )
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()
    except Exception as e:
        logger.warning(f"Groq Whisper transcription failed: {e}")
        return ""


def local_whisper_transcribe(audio_bytes: bytes) -> str:
    """Local Whisper STT (optional). Returns '' when unavailable."""
    try:
        import whisper  # type: ignore
        import tempfile
        import os
        model = whisper.load_model("base")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name
        try:
            result = model.transcribe(tmp)
            return (result.get("text") or "").strip()
        finally:
            os.unlink(tmp)
    except Exception as e:
        logger.warning(f"Local Whisper transcription failed: {e}")
        return ""
