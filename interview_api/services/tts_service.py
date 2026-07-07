"""Georgian text-to-speech for spoken interview questions."""

from __future__ import annotations

import asyncio
import logging
import os

from django.core.files.base import ContentFile

from interview_api.exceptions import TTSServiceError

logger = logging.getLogger(__name__)

DEFAULT_GEORGIAN_VOICE = "ka-GE-EkaNeural"


def _georgian_voice() -> str:
    return os.environ.get("INTERVIEW_TTS_VOICE", DEFAULT_GEORGIAN_VOICE).strip() or DEFAULT_GEORGIAN_VOICE


async def _synthesize_async(text: str, voice: str) -> bytes:
    try:
        import edge_tts
    except ImportError as exc:
        raise TTSServiceError("edge-tts is not installed.") from exc

    audio_bytes = bytearray()
    communicate = edge_tts.Communicate(text.strip(), voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])
    if not audio_bytes:
        raise TTSServiceError("TTS returned empty audio.")
    return bytes(audio_bytes)


def synthesize_question_audio(text: str) -> ContentFile:
    """Synthesize Georgian interviewer speech as MP3."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise TTSServiceError("Cannot synthesize empty question text.")

    voice = _georgian_voice()
    try:
        audio_bytes = asyncio.run(_synthesize_async(cleaned, voice))
    except TTSServiceError:
        raise
    except Exception as exc:
        logger.exception("Georgian TTS failed")
        raise TTSServiceError(f"Georgian speech synthesis failed: {exc}") from exc

    return ContentFile(audio_bytes, name="question.mp3")
