"""
Authenticate requests using breneo-api JWT (Bearer token).

Validates by calling BRENEO_API_BASE_URL + BRENEO_API_ME_PATH, or decodes a shared
JWT secret when BRENEO_JWT_SECRET is set. For local development (DEBUG only),
accepts Bearer tokens of the form ``dev:<user_id>``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import requests
from django.conf import settings
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)


@dataclass
class BreneoUser:
    """Lightweight user object from breneo-api (not a Django User)."""

    id: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def __str__(self) -> str:
        return self.id


def get_breneo_user_id(request) -> str | None:
    user = getattr(request, "user", None)
    if isinstance(user, BreneoUser):
        return str(user.id)
    return None


def _extract_user_id(payload: dict[str, Any]) -> str | None:
    if not payload:
        return None
    for key in ("id", "user_id", "sub"):
        val = payload.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    user = payload.get("user")
    if isinstance(user, dict):
        for key in ("id", "user_id"):
            val = user.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    return None


def _user_from_payload(payload: dict[str, Any]) -> BreneoUser | None:
    uid = _extract_user_id(payload)
    if not uid:
        return None
    user_block = payload.get("user") if isinstance(payload.get("user"), dict) else payload
    return BreneoUser(
        id=uid,
        email=user_block.get("email") or payload.get("email"),
        first_name=user_block.get("first_name") or payload.get("first_name"),
        last_name=user_block.get("last_name") or payload.get("last_name"),
        raw=payload,
    )


def resolve_breneo_user_from_token(token: str) -> BreneoUser | None:
    """Resolve a Breneo user from a bearer token (used by auth class and tests)."""
    token = (token or "").strip()
    if not token:
        return None

    if getattr(settings, "DEBUG", False):
        dev_prefix = getattr(settings, "BRENEO_AUTH_DEV_TOKEN_PREFIX", "dev:")
        if token.startswith(dev_prefix):
            uid = token[len(dev_prefix) :].strip()
            if uid:
                return BreneoUser(id=uid)

    jwt_secret = (
        os.environ.get("BRENEO_JWT_SECRET", "").strip()
        or os.environ.get("JWT_SECRET", "").strip()
    )
    if jwt_secret:
        user = _resolve_from_jwt_secret(token, jwt_secret)
        if user:
            return user

    base_url = os.environ.get("BRENEO_API_BASE_URL", "").strip().rstrip("/")
    if base_url:
        return _resolve_from_breneo_api(token, base_url)

    return None


def _resolve_from_jwt_secret(token: str, secret: str) -> BreneoUser | None:
    try:
        import jwt
    except ImportError:
        logger.warning("PyJWT not installed; cannot decode BRENEO_JWT_SECRET tokens")
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256", "HS384", "HS512"],
            options={"verify_aud": False},
        )
    except Exception as exc:
        logger.debug("JWT decode failed: %s", exc)
        return None
    return _user_from_payload(payload if isinstance(payload, dict) else {})


def _resolve_from_breneo_api(token: str, base_url: str) -> BreneoUser | None:
    me_path = os.environ.get("BRENEO_API_ME_PATH", "/api/auth/me").strip()
    if not me_path.startswith("/"):
        me_path = "/" + me_path
    url = f"{base_url}{me_path}"
    timeout = int(os.environ.get("BRENEO_API_TIMEOUT_SECONDS", "10") or "10")
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.warning("breneo-api auth request failed: %s", exc)
        return None
    if response.status_code != 200:
        logger.debug("breneo-api /me returned %s", response.status_code)
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
        data = data["data"]
    return _user_from_payload(data if isinstance(data, dict) else {})


class BreneoJWTAuthentication(authentication.BaseAuthentication):
    """
    DRF authentication: Authorization: Bearer <breneo-api JWT>.
    Sets request.user to BreneoUser. Returns None when header is absent (optional auth).
    """

    keyword = "Bearer"
    require_header = False

    def authenticate(self, request):
        header = authentication.get_authorization_header(request)
        if not header:
            if self.require_header:
                raise exceptions.AuthenticationFailed(
                    "Authentication credentials were not provided."
                )
            return None
        parts = header.decode("utf-8").split()
        if len(parts) != 2 or parts[0] != self.keyword:
            if self.require_header:
                raise exceptions.AuthenticationFailed("Invalid authorization header.")
            return None
        user = resolve_breneo_user_from_token(parts[1])
        if user is None:
            raise exceptions.AuthenticationFailed("Invalid or expired authentication token.")
        return (user, parts[1])


class BreneoJWTRequiredAuthentication(BreneoJWTAuthentication):
    """Same as BreneoJWTAuthentication but returns 401 when Authorization is missing."""

    require_header = True
