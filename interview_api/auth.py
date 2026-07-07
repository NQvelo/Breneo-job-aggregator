"""Resolve the Breneo user id string from an authenticated request."""

from __future__ import annotations

from jobs.authentication.breneo_auth import BreneoUser, get_breneo_user_id
from jobs.breneo_user import external_user_id_from_request


def resolve_user_id(request) -> str | None:
    """Return the Breneo user id as plain text (JWT user, header, or body/query)."""
    breneo_id = get_breneo_user_id(request)
    if breneo_id:
        return breneo_id

    user = getattr(request, "user", None)
    if isinstance(user, BreneoUser):
        return str(user.id)

    external_id = external_user_id_from_request(request)
    if external_id:
        return external_id

    if user is not None and getattr(user, "is_authenticated", False):
        for attr in ("id", "pk", "username"):
            value = getattr(user, attr, None)
            if value is not None and str(value).strip():
                return str(value).strip()

    return None
