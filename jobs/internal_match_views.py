"""
Internal match API for breneo-api. Shared secret header, never the browser.

POST /internal/job-matches
POST /internal/job-matches/one
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .match_candidates import candidate_jobs
from .match_score import SnapshotError, parse_snapshot, score_job
from .models import Job

MATCH_CACHE_TTL_SECONDS = 15 * 60
_NO_STORE = {"Cache-Control": "no-store"}


class HasInternalKey(BasePermission):
    """X-Internal-Key must match INTERNAL_API_KEY. Server to server only."""

    def has_permission(self, request, view):
        expected = (getattr(settings, "INTERNAL_API_KEY", "") or "").strip()
        provided = (request.headers.get("X-Internal-Key") or "").strip()
        if not expected or not provided or not hmac.compare_digest(provided, expected):
            raise NotAuthenticated("Not authorized.")
        return True


def _snapshot_and_body(data):
    if not isinstance(data, dict):
        raise SnapshotError("JSON object required")
    snapshot_payload = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else data
    return parse_snapshot(snapshot_payload), data, snapshot_payload


def _scope(data, snapshot_payload) -> str:
    scope = data.get("scope", snapshot_payload.get("scope"))
    if scope not in ("georgia", "worldwide"):
        raise SnapshotError('scope must be "georgia" or "worldwide"')
    return scope


def _limit(data, snapshot_payload) -> int:
    if "limit" in data:
        raw = data.get("limit")
    elif "limit" in snapshot_payload and snapshot_payload is not data:
        raw = snapshot_payload.get("limit")
    else:
        raise SnapshotError("limit is required")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise SnapshotError("limit must be a positive integer")
    return raw


def _job_id(data, snapshot_payload):
    if "jobId" in data:
        raw = data.get("jobId")
    elif "job_id" in data:
        raw = data.get("job_id")
    elif snapshot_payload is not data and "jobId" in snapshot_payload:
        raw = snapshot_payload.get("jobId")
    elif snapshot_payload is not data and "job_id" in snapshot_payload:
        raw = snapshot_payload.get("job_id")
    else:
        raise SnapshotError("jobId is required")
    if isinstance(raw, bool):
        raise SnapshotError("jobId must be an integer")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    raise SnapshotError("jobId must be an integer")


def _cache_key(user_id: str, profile_version: str, scope: str, limit: int) -> str:
    raw = f"{user_id}\0{profile_version}\0{scope}\0{limit}".encode()
    return "jobmatch:v2:" + hashlib.sha256(raw).hexdigest()


_WORK_MODE_VALUES = {"remote", "hybrid", "on-site", "onsite", "on site", "unknown"}
_EMPLOYMENT_KEYS = (
    "employment_type_note",
    "employment_type",
    "job_employment_type",
    "job_type",
    "commitment",
    "type",
)


def _employment_type(job) -> str | None:
    raw = job.raw if isinstance(job.raw, dict) else {}
    submitted = raw.get("employer_submitted")
    sources = [submitted, raw] if isinstance(submitted, dict) else [raw]
    for source in sources:
        for key in _EMPLOYMENT_KEYS:
            value = source.get(key)
            if not isinstance(value, str):
                continue
            text = value.strip()
            if text and text.lower() not in _WORK_MODE_VALUES:
                return text
    return None


def job_match_payload(job, score, request=None) -> dict:
    from .logo_url import resolved_company_logo_url

    posted = job.posted_at
    logo = resolved_company_logo_url(job.company, request)
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company.name,
        "company_logo": logo or None,
        "location": job.location,
        "posted_at": posted.isoformat() if posted else None,
        "salary": job.salary or None,
        "employment_type": _employment_type(job),
        "work_mode": job.work_mode or None,
        "workplace_type": job.workplace_type or None,
        "match_percent": score.match_percent,
        "skills_percent": score.skills_percent,
        "experience_percent": score.experience_percent,
        "industry_percent": score.industry_percent,
    }


def _ranked_jobs(scope: str, snapshot, limit: int, request=None) -> list[dict]:
    jobs = list(candidate_jobs(scope, snapshot.seniority, snapshot.skills))
    ranked = []
    for job in jobs:
        score = score_job(job, snapshot)
        posted = job.posted_at
        posted_key = posted.timestamp() if posted is not None else float("-inf")
        ranked.append((score.match_percent, posted_key, job.id, job_match_payload(job, score, request)))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[3] for item in ranked[:limit]]


class InternalMatchView(APIView):
    """Shared-secret JSON API. Not part of the public schema."""

    authentication_classes = []
    permission_classes = [HasInternalKey]

    def get_authenticate_header(self, request):
        return "InternalKey"


@method_decorator(never_cache, name="dispatch")
class JobMatchesView(InternalMatchView):
    """Cached list of the top matches for one user snapshot and scope."""

    @extend_schema(exclude=True)
    def post(self, request):
        try:
            snapshot, body, snapshot_payload = _snapshot_and_body(request.data)
            scope = _scope(body, snapshot_payload)
            limit = _limit(body, snapshot_payload)
        except SnapshotError as exc:
            return Response({"error": str(exc)}, status=400, headers=_NO_STORE)

        key = _cache_key(snapshot.user_id, snapshot.profile_version, scope, limit)
        cached = cache.get(key)
        if cached is not None:
            return Response(cached, headers=_NO_STORE)

        payload = _ranked_jobs(scope, snapshot, limit, request)
        cache.set(key, payload, MATCH_CACHE_TTL_SECONDS)
        return Response(payload, headers=_NO_STORE)


@method_decorator(never_cache, name="dispatch")
class JobMatchOneView(InternalMatchView):
    """Fresh score for one job. Not cached. Same integer as the list."""

    @extend_schema(exclude=True)
    def post(self, request):
        try:
            snapshot, body, snapshot_payload = _snapshot_and_body(request.data)
            job_id = _job_id(body, snapshot_payload)
        except SnapshotError as exc:
            return Response({"error": str(exc)}, status=400, headers=_NO_STORE)
        try:
            job = Job.objects.select_related("company").only(
                "id",
                "title",
                "location",
                "posted_at",
                "skills_required",
                "seniority",
                "min_years_experience",
                "industry_tags",
                "languages_required",
                "salary",
                "work_mode",
                "workplace_type",
                "raw",
                "company__name",
                "company__logo",
                "company__logo_upload",
                "company__employer_created",
            ).get(pk=job_id)
        except Job.DoesNotExist:
            return Response({"error": "Job not found."}, status=404, headers=_NO_STORE)
        return Response(job_match_payload(job, score_job(job, snapshot), request), headers=_NO_STORE)
