"""
Interview API auth — BFF / server-only (same trust model as employer jobs + applications).

The browser calls breneoapp BFF with the user's Breneo JWT. The BFF verifies the session,
then calls job-aggregator with:

  X-Employer-Key: <EMPLOYER_POST_SECRET>   (same as employer job POST)
  OR X-Application-Key: <APPLICATION_API_SECRET or EMPLOYER_POST_SECRET>
  user_id: <breneo user id>   (JSON body on start, query on submit-audio)

Direct aggregator calls (Postman / tests) may still use Breneo JWT or dev:<user_id> when DEBUG.
"""

from __future__ import annotations

import hmac
import logging

from rest_framework import authentication, exceptions

from jobs.authentication.application_auth import application_api_secret
from jobs.breneo_user import external_user_id_from_request

logger = logging.getLogger(__name__)


def _server_secret_matches(request) -> bool:
    secret = application_api_secret()
    if not secret:
        return False

    for header in ("X-Application-Key", "X-Employer-Key"):
        token = (request.headers.get(header) or "").strip()
        if token and hmac.compare_digest(token, secret):
            return True

    auth_header = authentication.get_authorization_header(request).decode("utf-8")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token and hmac.compare_digest(token, secret):
            return True

    return False


class InterviewBFFAuthentication(authentication.BaseAuthentication):
    """Trusted BFF: X-Employer-Key / X-Application-Key (+ optional Bearer) + user_id."""

    def authenticate(self, request):
        if not _server_secret_matches(request):
            return None

        uid = external_user_id_from_request(request)
        if not uid:
            return None

        from jobs.authentication.breneo_auth import BreneoUser

        return (BreneoUser(id=uid), "bff")


class InterviewBFFRequiredAuthentication(InterviewBFFAuthentication):
    """401 when server secret is present but user_id is missing (BFF misconfiguration)."""

    def authenticate(self, request):
        secret = application_api_secret()
        if not secret:
            return None

        has_secret_header = any(
            (request.headers.get(header) or "").strip()
            for header in ("X-Application-Key", "X-Employer-Key")
        )
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        has_bearer = auth_header.startswith("Bearer ") and auth_header[7:].strip()

        if not has_secret_header and not has_bearer:
            return None

        if not _server_secret_matches(request):
            return None

        uid = external_user_id_from_request(request)
        if not uid:
            raise exceptions.AuthenticationFailed(
                "Missing user id. Send user_id or external_user_id in body/query after "
                "verifying the user session in your BFF."
            )

        from jobs.authentication.breneo_auth import BreneoUser

        return (BreneoUser(id=uid), "bff")
