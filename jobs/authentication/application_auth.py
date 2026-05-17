"""
Application API auth without breneo-api JWT (separate databases).

Two supported modes:
1. Signed user headers (browser → job-aggregator only):
   X-Breneo-User-Id, X-Breneo-Timestamp, X-Breneo-Signature
   Signature = HMAC-SHA256(APPLICATION_SIGNATURE_SECRET, "{user_id}:{timestamp}")

   breneo-api generates these on login/me using the SAME secret and returns them to the
   frontend (e.g. applicationAuth in login JSON). Frontend stores and sends on each request.

2. BFF / server (optional):
   X-Application-Key + external_user_id (query/body) — same secret family as employer key.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass

from rest_framework import authentication, exceptions

from ..breneo_user import external_user_id_from_request

logger = logging.getLogger(__name__)


@dataclass
class ApplicationUser:
    """Breneo user id authorized for job-application routes."""

    id: str

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False


def _signature_secret() -> str:
    return (
        os.environ.get("APPLICATION_SIGNATURE_SECRET", "").strip()
        or os.environ.get("BRENEO_APPLICATION_SIGNATURE_SECRET", "").strip()
    )


def _application_api_secret() -> str:
    return (
        os.environ.get("APPLICATION_API_SECRET", "").strip()
        or os.environ.get("EMPLOYER_POST_SECRET", "").strip()
    )


def sign_application_request(user_id: str, timestamp: int | None = None) -> str:
    secret = _signature_secret()
    if not secret:
        raise ValueError("APPLICATION_SIGNATURE_SECRET is not configured")
    ts = int(timestamp if timestamp is not None else time.time())
    msg = f"{user_id}:{ts}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def verify_application_signature(user_id: str, timestamp: str | int, signature: str) -> bool:
    secret = _signature_secret()
    if not secret or not user_id or not signature:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    max_age = int(os.environ.get("APPLICATION_SIGNATURE_MAX_AGE_SECONDS", "900") or "900")
    if abs(time.time() - ts) > max_age:
        return False
    expected = sign_application_request(user_id, ts)
    return hmac.compare_digest(expected, signature)


def build_application_auth_headers(user_id: str) -> dict[str, str]:
    """Headers for frontend to send to job-aggregator (values from breneo login/me)."""
    ts = int(time.time())
    return {
        "X-Breneo-User-Id": str(user_id),
        "X-Breneo-Timestamp": str(ts),
        "X-Breneo-Signature": sign_application_request(user_id, ts),
    }


def get_application_user_id(request) -> str | None:
    user = getattr(request, "user", None)
    if isinstance(user, ApplicationUser):
        return str(user.id)
    return None


class ApplicationUserAuthentication(authentication.BaseAuthentication):
    """
    Validate signed user headers or BFF application key + external_user_id.
    """

    def authenticate(self, request):
        bff_secret = _application_api_secret()
        app_key = (request.headers.get("X-Application-Key") or "").strip()
        if bff_secret and app_key and hmac.compare_digest(app_key, bff_secret):
            uid = external_user_id_from_request(request)
            if uid:
                return (ApplicationUser(id=uid), "bff")

        uid = (request.headers.get("X-Breneo-User-Id") or "").strip()
        ts = (request.headers.get("X-Breneo-Timestamp") or "").strip()
        sig = (request.headers.get("X-Breneo-Signature") or "").strip()
        if uid and ts and sig and verify_application_signature(uid, ts, sig):
            return (ApplicationUser(id=uid), "signature")

        return None


class ApplicationUserRequiredAuthentication(ApplicationUserAuthentication):
    """Require signed headers or BFF key; 401 if missing/invalid."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            raise exceptions.AuthenticationFailed(
                "Invalid application auth. Send X-Breneo-User-Id, X-Breneo-Timestamp, "
                "and X-Breneo-Signature from breneo login, or call via server with "
                "X-Application-Key and external_user_id."
            )
        return result
