"""
Application API auth — BFF / server-only (safe mode).

The browser must NOT call apply/list/withdraw directly with secrets.
Your Next.js / breneo backend verifies the user session, then calls job-aggregator with:

  X-Application-Key: <APPLICATION_API_SECRET or EMPLOYER_POST_SECRET>
  external_user_id: <breneo user id>   (query, body, or header X-Breneo-User-Id)

Never put the application key in frontend env (NEXT_PUBLIC_*).
"""

from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass

from rest_framework import authentication, exceptions

from ..breneo_user import external_user_id_from_request

logger = logging.getLogger(__name__)


@dataclass
class ApplicationUser:
    """Breneo user id authorized for job-application routes (via trusted BFF)."""

    id: str

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False


def application_api_secret() -> str:
    return (
        os.environ.get("APPLICATION_API_SECRET", "").strip()
        or os.environ.get("EMPLOYER_POST_SECRET", "").strip()
    )


def get_application_user_id(request) -> str | None:
    user = getattr(request, "user", None)
    if isinstance(user, ApplicationUser):
        return str(user.id)
    return None


def _user_id_from_request(request) -> str:
    uid = external_user_id_from_request(request)
    if uid:
        return uid
    return (request.headers.get("X-Breneo-User-Id") or "").strip()


class ApplicationBFFAuthentication(authentication.BaseAuthentication):
    """
    Trusted server calls only: valid X-Application-Key + breneo user id.
    """

    def authenticate(self, request):
        secret = application_api_secret()
        if not secret:
            logger.warning("APPLICATION_API_SECRET / EMPLOYER_POST_SECRET is not set")
            return None

        app_key = (request.headers.get("X-Application-Key") or "").strip()
        if not app_key or not hmac.compare_digest(app_key, secret):
            return None

        uid = _user_id_from_request(request)
        if not uid:
            return None

        return (ApplicationUser(id=uid), "bff")


class ApplicationBFFRequiredAuthentication(ApplicationBFFAuthentication):
    """Same as ApplicationBFFAuthentication; 401 if key or user id is missing."""

    def authenticate(self, request):
        secret = application_api_secret()
        if not secret:
            raise exceptions.AuthenticationFailed(
                "Application API is not configured. Set APPLICATION_API_SECRET on the server."
            )

        app_key = (request.headers.get("X-Application-Key") or "").strip()
        if not app_key or not hmac.compare_digest(app_key, secret):
            raise exceptions.AuthenticationFailed(
                "Invalid or missing X-Application-Key. Call from your backend (BFF) only; "
                "do not expose this key in the browser."
            )

        uid = _user_id_from_request(request)
        if not uid:
            raise exceptions.AuthenticationFailed(
                "Missing user id. Send external_user_id (query/body) or X-Breneo-User-Id "
                "after verifying the user session in your BFF."
            )

        return (ApplicationUser(id=uid), "bff")
