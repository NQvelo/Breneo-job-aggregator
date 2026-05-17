"""Fetch breneo-api user profiles for applicant enrichment."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


def fetch_user_profiles(user_ids: list[str], *, auth_token: str | None = None) -> dict[str, dict[str, Any]]:
    """
    Return a map of user_id -> profile dict.
    Falls back to minimal {id} objects when breneo-api is unavailable.
    """
    unique_ids = sorted({uid for uid in user_ids if uid})
    if not unique_ids:
        return {}

    base_url = os.environ.get("BRENEO_API_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return {uid: {"id": uid} for uid in unique_ids}

    profiles: dict[str, dict[str, Any]] = {uid: {"id": uid} for uid in unique_ids}
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    bulk_path = os.environ.get("BRENEO_API_USERS_BULK_PATH", "").strip()
    if bulk_path:
        if not bulk_path.startswith("/"):
            bulk_path = "/" + bulk_path
        try:
            response = requests.post(
                f"{base_url}{bulk_path}",
                json={"ids": unique_ids},
                headers=headers,
                timeout=int(os.environ.get("BRENEO_API_TIMEOUT_SECONDS", "10") or "10"),
            )
            if response.status_code == 200:
                data = response.json()
                users = data.get("data") or data.get("users") or data
                if isinstance(users, list):
                    for item in users:
                        if isinstance(item, dict) and item.get("id"):
                            profiles[str(item["id"])] = item
                    return profiles
        except requests.RequestException as exc:
            logger.warning("breneo bulk user fetch failed: %s", exc)

    single_path_template = os.environ.get(
        "BRENEO_API_USER_PATH_TEMPLATE",
        "/api/users/{user_id}",
    )
    timeout = int(os.environ.get("BRENEO_API_TIMEOUT_SECONDS", "10") or "10")
    for uid in unique_ids:
        path = single_path_template.format(user_id=uid)
        if not path.startswith("/"):
            path = "/" + path
        try:
            response = requests.get(f"{base_url}{path}", headers=headers, timeout=timeout)
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                    payload = payload["data"]
                if isinstance(payload, dict):
                    profiles[uid] = payload
        except requests.RequestException:
            continue
    return profiles
