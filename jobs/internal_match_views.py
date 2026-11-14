"""
Internal match API for breneo-api. Shared secret header, never the browser.

POST /internal/job-matches
POST /internal/job-matches/one
"""

from __future__ import annotations

import hashlib
import hmac
import json

from django.conf import settings
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .match_candidates import search_candidate_jobs
from .match_score import SnapshotError, parse_snapshot, score_job
from .models import Job
from .user_match_store import matches_for_request, ranked_scored

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
    return [
        job_match_payload(job, score, request)
        for _percent, _posted, _job_id, job, score in ranked_scored(scope, snapshot, limit)
    ]


class InternalMatchView(APIView):
    """Shared-secret JSON API. Not part of the public schema."""

    authentication_classes = []
    permission_classes = [HasInternalKey]

    def get_authenticate_header(self, request):
        return "InternalKey"


@method_decorator(never_cache, name="dispatch")
class JobMatchesView(InternalMatchView):
    """Stored matches for one user snapshot and scope. New jobs are appended once a day."""

    @extend_schema(exclude=True)
    def post(self, request):
        try:
            snapshot, body, snapshot_payload = _snapshot_and_body(request.data)
            scope = _scope(body, snapshot_payload)
            limit = _limit(body, snapshot_payload)
        except SnapshotError as exc:
            return Response({"error": str(exc)}, status=400, headers=_NO_STORE)

        payload = matches_for_request(snapshot, scope, limit, request)
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


def _text_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list):
        parts = value
    else:
        return []
    return [str(item).strip() for item in parts if str(item).strip()]


def _search_filters(body: dict) -> dict:
    date_posted = body.get("datePosted", body.get("date_posted", "all"))
    if not isinstance(date_posted, str):
        date_posted = "all"
    return {
        "query": body.get("query") if isinstance(body.get("query"), str) else "",
        "titles": _text_list(body.get("title", body.get("titles"))),
        "cities": _text_list(body.get("city", body.get("cities"))),
        "location_countries": _text_list(
            body.get("locationCountry", body.get("location_country"))
        ),
        "work_modes": _text_list(body.get("workMode", body.get("work_mode"))),
        "job_seniorities": _text_list(body.get("jobSeniority", body.get("job_seniority"))),
        "role_categories": _text_list(body.get("roleCategory", body.get("role_category"))),
        "companies": _text_list(body.get("companyNames", body.get("company_names"))),
        "date_posted": date_posted.strip().lower() or "all",
    }


def _search_cache_key(user_id: str, profile_version: str, filters: dict, limit: int) -> str:
    raw = json.dumps(
        {"userId": user_id, "profileVersion": profile_version, "filters": filters, "limit": limit},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "jobmatch:v2:search:" + hashlib.sha256(raw).hexdigest()


@method_decorator(never_cache, name="dispatch")
class JobMatchSearchView(InternalMatchView):
    """Ranked matches for a search. Drops 0% and returns highest match first."""

    @extend_schema(exclude=True)
    def post(self, request):
        try:
            snapshot, body, snapshot_payload = _snapshot_and_body(request.data)
            limit = _limit(body, snapshot_payload)
        except SnapshotError as exc:
            return Response({"error": str(exc)}, status=400, headers=_NO_STORE)
        if limit > 300:
            return Response({"error": "limit must be at most 300."}, status=400, headers=_NO_STORE)

        filters = _search_filters(body if body is snapshot_payload else {**snapshot_payload, **body})
        key = _search_cache_key(snapshot.user_id, snapshot.profile_version, filters, limit)
        cached = cache.get(key)
        if cached is not None:
            return Response(cached, headers=_NO_STORE)

        ranked = []
        for job in search_candidate_jobs(snapshot.seniority, snapshot.skills, filters):
            score = score_job(job, snapshot)
            if score.match_percent <= 0:
                continue
            posted = job.posted_at
            posted_key = posted.timestamp() if posted is not None else float("-inf")
            ranked.append((score.match_percent, posted_key, job.id, job_match_payload(job, score, request)))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        payload = [item[3] for item in ranked[:limit]]
        cache.set(key, payload, MATCH_CACHE_TTL_SECONDS)
        return Response(payload, headers=_NO_STORE)
