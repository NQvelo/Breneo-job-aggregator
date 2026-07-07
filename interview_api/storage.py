"""Storage backend for interview audio uploads."""

from __future__ import annotations

import os


def interview_audio_storage():
    """Use Cloudinary video storage for WebM/audio; fall back to default locally."""
    if os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip():
        from cloudinary_storage.storage import VideoMediaCloudinaryStorage

        return VideoMediaCloudinaryStorage()
    from django.core.files.storage import default_storage

    return default_storage
