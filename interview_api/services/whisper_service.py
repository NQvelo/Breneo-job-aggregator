"""Speech-to-text via OpenAI or Groq Whisper API."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from interview_api.exceptions import WhisperTranscriptionError

logger = logging.getLogger(__name__)


def _whisper_settings() -> tuple[str, str, str]:
    provider = (
        os.environ.get("INTERVIEW_WHISPER_PROVIDER", "").strip().lower()
        or getattr(settings, "INTERVIEW_WHISPER_PROVIDER", "groq")
    ).lower()

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise WhisperTranscriptionError("OPENAI_API_KEY is not configured.")
        model = os.environ.get("OPENAI_WHISPER_MODEL", "whisper-1").strip()
        url = "https://api.openai.com/v1/audio/transcriptions"
        return url, api_key, model

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise WhisperTranscriptionError("GROQ_API_KEY is not configured.")
    model = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3").strip()
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    return url, api_key, model


def _guess_filename(uploaded_file: UploadedFile) -> str:
    name = getattr(uploaded_file, "name", None) or "recording.webm"
    return Path(name).name or "recording.webm"


def _guess_content_type(uploaded_file: UploadedFile, filename: str) -> str:
    content_type = getattr(uploaded_file, "content_type", None)
    if content_type:
        return content_type
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def transcribe_audio(uploaded_file: UploadedFile) -> str:
    """Transcribe an uploaded audio/video blob using Whisper (Georgian)."""
    if uploaded_file is None:
        raise WhisperTranscriptionError("No audio file provided.")

    url, api_key, model = _whisper_settings()
    timeout = int(os.environ.get("INTERVIEW_WHISPER_TIMEOUT_SECONDS", "120") or "120")
    filename = _guess_filename(uploaded_file)
    content_type = _guess_content_type(uploaded_file, filename)

    uploaded_file.seek(0)
    files = {"file": (filename, uploaded_file, content_type)}
    data = {
        "model": model,
        "language": "ka",
        "response_format": "json",
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        response = requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.exception("Whisper request failed")
        raise WhisperTranscriptionError(f"Whisper request failed: {exc}") from exc

    if response.status_code >= 400:
        logger.error("Whisper error %s: %s", response.status_code, response.text[:500])
        raise WhisperTranscriptionError(f"Whisper API returned HTTP {response.status_code}.")

    try:
        payload = response.json()
        text = (payload.get("text") or "").strip()
    except ValueError as exc:
        raise WhisperTranscriptionError("Whisper returned non-JSON response.") from exc

    if not text:
        raise WhisperTranscriptionError("Whisper returned an empty transcript.")

    return text
