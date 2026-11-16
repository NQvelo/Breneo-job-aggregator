"""Active in-app applications used to hide jobs from discovery lists."""

from __future__ import annotations

from django.core.cache import cache

from .models import JobApplication

_APPS_VERSION_TTL_SECONDS = 30 * 24 * 60 * 60


def active_applied_job_ids(user_id: str | None) -> set[int]:
    if not user_id:
        return set()
    return set(
        JobApplication.objects.filter(
            external_user_id=str(user_id),
            withdrawn_at__isnull=True,
        ).values_list("job_id", flat=True)
    )


def parse_exclude_job_ids(values) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for raw in values or []:
        text = str(raw).strip()
        if not text.isdigit():
            continue
        job_id = int(text)
        if job_id in seen:
            continue
        seen.add(job_id)
        ids.append(job_id)
    return ids


def _version_key(user_id: str) -> str:
    return f"jobmatch:appsver:{user_id}"


def applied_jobs_version(user_id: str | None) -> int:
    if not user_id:
        return 0
    value = cache.get(_version_key(str(user_id)))
    return int(value) if value else 0


def bump_applied_jobs_version(user_id: str | None) -> None:
    if not user_id:
        return
    key = _version_key(str(user_id))
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, _APPS_VERSION_TTL_SECONDS)
    else:
        cache.touch(key, _APPS_VERSION_TTL_SECONDS)
