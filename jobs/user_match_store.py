"""
Stored per-user job matches.

POST /internal/job-matches saves the snapshot and the first ranked page.
The daily cron re-ranks from the current job catalog and adds new jobs
without dropping older matches that are still active.
"""

from __future__ import annotations

from django.utils import timezone

from .match_candidates import _CARD_FIELDS, candidate_jobs
from .match_score import MatchScore, UserSnapshot, parse_snapshot, score_job
from .models import JOB_DEADLINE_TZ, Job, UserJobMatch, UserMatchSnapshot, visible_jobs_q


def snapshot_payload(snapshot: UserSnapshot) -> dict:
    return {
        "userId": snapshot.user_id,
        "profileVersion": snapshot.profile_version,
        "skills": snapshot.skills,
        "seniority": snapshot.seniority,
        "yearsExperienceTotal": snapshot.years_experience_total,
        "industryYears": snapshot.industry_years,
        "languages": snapshot.languages,
    }


def georgia_date(when=None):
    return (when or timezone.now()).astimezone(JOB_DEADLINE_TZ).date()


def ranked_scored(scope: str, snapshot: UserSnapshot, limit: int):
    jobs = list(candidate_jobs(scope, snapshot.seniority, snapshot.skills))
    ranked = []
    for job in jobs:
        score = score_job(job, snapshot)
        posted = job.posted_at
        posted_key = posted.timestamp() if posted is not None else float("-inf")
        ranked.append((score.match_percent, posted_key, job.id, job, score))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return ranked[:limit]


def _upsert_match(user_id: str, scope: str, job, score: MatchScore, now):
    match, created = UserJobMatch.objects.get_or_create(
        user_id=user_id,
        scope=scope,
        job=job,
        defaults={
            "match_percent": score.match_percent,
            "skills_percent": score.skills_percent,
            "experience_percent": score.experience_percent,
            "industry_percent": score.industry_percent,
            "first_matched_at": now,
            "last_scored_at": now,
        },
    )
    if created:
        return match
    match.match_percent = score.match_percent
    match.skills_percent = score.skills_percent
    match.experience_percent = score.experience_percent
    match.industry_percent = score.industry_percent
    match.last_scored_at = now
    match.save(
        update_fields=[
            "match_percent",
            "skills_percent",
            "experience_percent",
            "industry_percent",
            "last_scored_at",
        ]
    )
    return match


def merge_ranked(user_id: str, scope: str, snapshot: UserSnapshot, ranked, rescore_existing: bool):
    """Write today's ranked jobs. Keep older matches; rescore them when the profile changed."""
    now = timezone.now()
    seen = set()
    for _percent, _posted, job_id, job, score in ranked:
        _upsert_match(user_id, scope, job, score, now)
        seen.add(job_id)

    if not rescore_existing:
        return

    existing = (
        UserJobMatch.objects.filter(user_id=user_id, scope=scope)
        .exclude(job_id__in=seen)
        .select_related("job")
    )
    for match in existing:
        job = match.job
        if not job.is_active:
            continue
        score = score_job(job, snapshot)
        match.match_percent = score.match_percent
        match.skills_percent = score.skills_percent
        match.experience_percent = score.experience_percent
        match.industry_percent = score.industry_percent
        match.last_scored_at = now
        match.save(
            update_fields=[
                "match_percent",
                "skills_percent",
                "experience_percent",
                "industry_percent",
                "last_scored_at",
            ]
        )


def stored_payloads(user_id: str, scope: str, request=None) -> list[dict]:
    from .internal_match_views import job_match_payload

    only_fields = [
        "match_percent",
        "skills_percent",
        "experience_percent",
        "industry_percent",
        "job_id",
        *[f"job__{field}" for field in _CARD_FIELDS],
    ]
    rows = (
        UserJobMatch.objects.filter(
            user_id=user_id,
            scope=scope,
            job_id__in=Job.objects.filter(visible_jobs_q()).values("id"),
        )
        .select_related("job", "job__company")
        .only(*only_fields)
    )
    ranked = []
    for match in rows:
        job = match.job
        score = MatchScore(
            match_percent=match.match_percent,
            skills_percent=match.skills_percent,
            experience_percent=match.experience_percent,
            industry_percent=match.industry_percent,
        )
        posted = job.posted_at
        posted_key = posted.timestamp() if posted is not None else float("-inf")
        ranked.append((score.match_percent, posted_key, job.id, job_match_payload(job, score, request)))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[3] for item in ranked]


def refresh_matches(snapshot: UserSnapshot, scope: str, limit: int, rescore_existing: bool = False) -> UserMatchSnapshot:
    ranked = ranked_scored(scope, snapshot, limit)
    merge_ranked(snapshot.user_id, scope, snapshot, ranked, rescore_existing=rescore_existing)
    profile, _created = UserMatchSnapshot.objects.update_or_create(
        user_id=snapshot.user_id,
        scope=scope,
        defaults={
            "profile_version": snapshot.profile_version,
            "snapshot": snapshot_payload(snapshot),
            "match_limit": limit,
            "last_refreshed_at": timezone.now(),
        },
    )
    return profile


def matches_for_request(snapshot: UserSnapshot, scope: str, limit: int, request=None) -> list[dict]:
    profile = UserMatchSnapshot.objects.filter(user_id=snapshot.user_id, scope=scope).first()
    profile_changed = profile is None or profile.profile_version != snapshot.profile_version
    due_today = profile is None or profile.last_refreshed_at is None or georgia_date(profile.last_refreshed_at) < georgia_date()
    if profile_changed or due_today:
        refresh_matches(snapshot, scope, limit, rescore_existing=profile_changed and profile is not None)
    elif profile is not None and (profile.match_limit != limit or profile.snapshot != snapshot_payload(snapshot)):
        profile.match_limit = limit
        profile.snapshot = snapshot_payload(snapshot)
        profile.profile_version = snapshot.profile_version
        profile.save(update_fields=["match_limit", "snapshot", "profile_version", "updated_at"])
    return stored_payloads(snapshot.user_id, scope, request)


def refresh_all_stored_profiles() -> int:
    """Re-rank every stored snapshot against today's jobs and append new matches."""
    count = 0
    for profile in UserMatchSnapshot.objects.all().iterator():
        snapshot = parse_snapshot(profile.snapshot)
        refresh_matches(snapshot, profile.scope, profile.match_limit, rescore_existing=False)
        count += 1
    return count
