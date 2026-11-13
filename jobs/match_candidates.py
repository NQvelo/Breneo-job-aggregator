"""
Indexed candidate read for per-user job matching.

The database returns at most 300 active jobs. Scoring happens in memory on
that page only. skills_required is GIN-indexed on PostgreSQL; seniority is
btree-indexed. This module never iterates the jobs table.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import connections
from django.db.models import BooleanField, F, Q
from django.db.models.expressions import RawSQL
from django.utils import timezone

from .location_resolver import (
    coalesce_georgia_filter_values,
    georgia_country_jobs_q,
    q_for_country_param,
    q_for_place_param,
)
from .match_score import SENIORITY_RANK
from .models import Job
from .query_parser import parse_query_to_search_params

CANDIDATE_CAP = 300

_CARD_FIELDS = (
    "id",
    "title",
    "location",
    "posted_at",
    "skills_required",
    "seniority",
    "min_years_experience",
    "industry_tags",
    "languages_required",
    "is_active",
    "salary",
    "work_mode",
    "workplace_type",
    "raw",
    "company__name",
    "company__logo",
    "company__logo_upload",
    "company__employer_created",
)


def seniority_window(user_seniority: str) -> list[str] | None:
    """Levels within one step of the user. None when the user level is unknown."""
    if user_seniority not in SENIORITY_RANK:
        return None
    index = SENIORITY_RANK[user_seniority]
    return [
        level
        for level, rank in SENIORITY_RANK.items()
        if abs(rank - index) <= 1
    ]


def _with_shared_skill(qs, skills: list[str]):
    """Jobs whose stored required skills share one normalized skill with the user."""
    vendor = connections[qs.db].vendor
    if vendor == "postgresql":
        shared = Q()
        for skill in skills:
            shared |= Q(skills_required__contains=[skill])
        return qs.filter(shared)
    table = Job._meta.db_table
    placeholders = ", ".join(["%s"] * len(skills))
    sql = (
        f"EXISTS (SELECT 1 FROM json_each({table}.skills_required) "
        f"WHERE json_each.value IN ({placeholders}))"
    )
    return qs.annotate(
        _shared_skill=RawSQL(sql, list(skills), output_field=BooleanField())
    ).filter(_shared_skill=True)


def candidate_jobs(scope: str, user_seniority: str, user_skills: list[str]):
    """
    Active jobs in scope, capped at 300, newest posted first.

    Seniority: within one level of the user, or null. Skipped when the user
    seniority is unknown. Skill overlap is required when the user has skills.
    """
    if scope == "georgia":
        qs = Job.objects.filter(georgia_country_jobs_q())
    elif scope == "worldwide":
        qs = Job.objects.exclude(georgia_country_jobs_q())
    else:
        raise ValueError("scope must be georgia or worldwide")
    qs = qs.filter(is_active=True)
    window = seniority_window(user_seniority)
    if window is not None:
        qs = qs.filter(
            Q(seniority__in=window)
            | Q(seniority__isnull=True)
            | Q(seniority="")
            | Q(seniority="unknown")
        )
    if user_skills:
        qs = _with_shared_skill(qs, user_skills)
    return (
        qs.select_related("company")
        .only(*_CARD_FIELDS)
        .order_by(F("posted_at").desc(nulls_last=True), "-id")[:CANDIDATE_CAP]
    )


def _card_page(qs):
    return (
        qs.select_related("company")
        .only(*_CARD_FIELDS)
        .order_by(F("posted_at").desc(nulls_last=True), "-id")[:CANDIDATE_CAP]
    )


def _apply_match_window(qs, user_seniority: str, user_skills: list[str]):
    window = seniority_window(user_seniority)
    if window is not None:
        qs = qs.filter(
            Q(seniority__in=window)
            | Q(seniority__isnull=True)
            | Q(seniority="")
            | Q(seniority="unknown")
        )
    if user_skills:
        qs = _with_shared_skill(qs, user_skills)
    return qs


def _icontains_any(field: str, values: list[str]) -> Q:
    query = Q()
    for value in values:
        query |= Q(**{f"{field}__icontains": value})
    return query


def apply_search_filters(qs, filters: dict):
    """Same title, place, and job filters as GET /api/search. Empty filters leave the set unchanged."""
    query_text = (filters.get("query") or "").strip()
    if query_text:
        parsed = parse_query_to_search_params(query_text)
        title_q = parsed.get("django_q_filters")
        if title_q:
            qs = qs.filter(title_q)

    titles = [item for item in filters.get("titles") or [] if item]
    if titles:
        qs = qs.filter(_icontains_any("title", titles))

    cities = coalesce_georgia_filter_values(list(filters.get("cities") or []))
    if cities:
        city_q = Q()
        for city in cities:
            place_q = q_for_place_param(city)
            city_q |= place_q if place_q is not None else Q(location__icontains=city)
        qs = qs.filter(city_q)

    countries = coalesce_georgia_filter_values(list(filters.get("location_countries") or []))
    if countries:
        country_q = Q()
        for country in countries:
            country_q |= q_for_country_param(country)
        qs = qs.filter(country_q)

    work_modes = [item.strip().lower() for item in filters.get("work_modes") or [] if str(item).strip()]
    if work_modes:
        mode_q = Q()
        for mode in work_modes:
            mode_q |= Q(work_mode__iexact=mode)
        qs = qs.filter(mode_q)

    job_levels = [item.strip().lower() for item in filters.get("job_seniorities") or [] if str(item).strip()]
    if job_levels:
        level_q = Q()
        for level in job_levels:
            level_q |= Q(seniority__iexact=level)
        qs = qs.filter(level_q)

    roles = [item for item in filters.get("role_categories") or [] if item]
    if roles:
        role_q = Q()
        for role in roles:
            role_q |= Q(role_category__iexact=role)
        qs = qs.filter(role_q)

    companies = [item for item in filters.get("companies") or [] if item]
    if companies:
        qs = qs.filter(_icontains_any("company__name", companies))

    date_posted = (filters.get("date_posted") or "all").strip().lower()
    if date_posted and date_posted != "all":
        now = timezone.now()
        if date_posted in ("today", "day"):
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_posted == "3days":
            start = now - timedelta(days=3)
        elif date_posted == "week":
            start = now - timedelta(days=7)
        elif date_posted == "month":
            start = now - timedelta(days=30)
        else:
            start = None
        if start is not None:
            qs = qs.filter(posted_at__gte=start)
    return qs


def search_candidate_jobs(user_seniority: str, user_skills: list[str], filters: dict):
    """
    Active jobs in both scopes that match the search filters and the user's
    skill and seniority window. Each scope is capped at 300, then scored by the caller.
    """
    seen = set()
    jobs = []
    for scope in ("georgia", "worldwide"):
        if scope == "georgia":
            qs = Job.objects.filter(georgia_country_jobs_q())
        else:
            qs = Job.objects.exclude(georgia_country_jobs_q())
        qs = apply_search_filters(qs.filter(is_active=True), filters)
        qs = _apply_match_window(qs, user_seniority, user_skills)
        for job in _card_page(qs):
            if job.id in seen:
                continue
            seen.add(job.id)
            jobs.append(job)
    return jobs
