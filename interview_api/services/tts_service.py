"""Georgian text-to-speech for spoken interview questions."""

from __future__ import annotations

import asyncio
import logging
import os

import requests
from django.core.files.base import ContentFile

from interview_api.exceptions import TTSServiceError

logger = logging.getLogger(__name__)

DEFAULT_GEORGIAN_VOICE = "ka-GE-EkaNeural"
DEFAULT_TTS_PROVIDER = "edge"


def _georgian_voice() -> str:
    return os.environ.get("INTERVIEW_TTS_VOICE", DEFAULT_GEORGIAN_VOICE).strip() or DEFAULT_GEORGIAN_VOICE


def _tts_provider() -> str:
    return os.environ.get("INTERVIEW_TTS_PROVIDER", DEFAULT_TTS_PROVIDER).strip().lower() or DEFAULT_TTS_PROVIDER


def _fallback_enabled() -> bool:
    return os.environ.get("INTERVIEW_TTS_FALLBACK", "true").strip().lower() == "true"


def _provider_chain() -> list[str]:
    """Ordered providers to try. Falls back to edge-tts unless disabled."""
    primary = _tts_provider()
    chain = [primary]
    if _fallback_enabled() and primary != "edge":
        chain.append("edge")
    return chain


def _elevenlabs_settings() -> tuple[str, str]:
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise TTSServiceError("ELEVENLABS_API_KEY is not configured.")

    voice_id = os.environ.get("INTERVIEW_TTS_ELEVENLABS_VOICE_ID", "").strip()
    if not voice_id:
        raise TTSServiceError("INTERVIEW_TTS_ELEVENLABS_VOICE_ID is not configured.")
    return api_key, voice_id


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


def _synthesize_elevenlabs(text: str) -> bytes:
    api_key, voice_id = _elevenlabs_settings()
    model_id = os.environ.get("INTERVIEW_TTS_ELEVENLABS_MODEL", "eleven_multilingual_v2").strip()
    timeout = int(os.environ.get("INTERVIEW_TTS_TIMEOUT_SECONDS", "60") or "60")

    payload = {
        "text": text.strip(),
        "model_id": model_id,
        "voice_settings": {
            "stability": float(os.environ.get("INTERVIEW_TTS_STABILITY", "0.45")),
            "similarity_boost": float(os.environ.get("INTERVIEW_TTS_SIMILARITY_BOOST", "0.8")),
            "style": float(os.environ.get("INTERVIEW_TTS_STYLE", "0.5")),
            "use_speaker_boost": os.environ.get("INTERVIEW_TTS_SPEAKER_BOOST", "true").lower() == "true",
        },
    }
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise TTSServiceError(f"ElevenLabs request failed: {exc}") from exc

    if response.status_code >= 400:
        snippet = response.text[:300] if response.text else "unknown error"
        raise TTSServiceError(f"ElevenLabs TTS failed with HTTP {response.status_code}: {snippet}")

    if not response.content:
        raise TTSServiceError("ElevenLabs returned empty audio.")
    return response.content


def _synthesize_edge(text: str) -> bytes:
    voice = _georgian_voice()
    return asyncio.run(_synthesize_async(text, voice))


def _synthesize_with_provider(provider: str, text: str) -> bytes:
    if provider == "elevenlabs":
        return _synthesize_elevenlabs(text)
    return _synthesize_edge(text)


def synthesize_question_audio(text: str) -> ContentFile:
    """Synthesize Georgian interviewer speech as MP3.

    Tries the configured provider first, then falls back to edge-tts if it fails
    (e.g. ElevenLabs rate limits, quota exhaustion, or outage).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise TTSServiceError("Cannot synthesize empty question text.")

    chain = _provider_chain()
    last_error: Exception | None = None

    for index, provider in enumerate(chain):
        try:
            audio_bytes = _synthesize_with_provider(provider, cleaned)
            if index > 0:
                logger.warning("Georgian TTS fell back to provider '%s'.", provider)
            return ContentFile(audio_bytes, name="question.mp3")
        except Exception as exc:
            last_error = exc
            is_last = index == len(chain) - 1
            logger.warning(
                "Georgian TTS provider '%s' failed%s: %s",
                provider,
                "" if is_last else "; trying fallback",
                exc,
            )

    raise TTSServiceError(f"Georgian speech synthesis failed: {last_error}") from last_error
