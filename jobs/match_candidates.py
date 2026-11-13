"""
Indexed candidate read for per-user job matching.

The database returns at most 300 active jobs. Scoring happens in memory on
that page only. skills_required is GIN-indexed on PostgreSQL; seniority is
btree-indexed. This module never iterates the jobs table.
"""

from __future__ import annotations

from django.db import connections
from django.db.models import BooleanField, F, Q
from django.db.models.expressions import RawSQL

from .location_resolver import georgia_country_jobs_q
from .match_score import SENIORITY_RANK
from .models import Job

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
    "company__name",
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
