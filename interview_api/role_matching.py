"""Resolve a requested interview to one prepared onboarding role."""

from __future__ import annotations

from interview_api.exceptions import InterviewRoleNotFound
from interview_api.models import InterviewRole
from interview_api.role_catalog import INTERVIEW_ROLES, match_role_slug

_TITLES = {slug: title for slug, title, _title_ka in INTERVIEW_ROLES}


def resolve_interview_role(*, role_slug: str = "", job_position: str = "", job=None) -> InterviewRole:
    slug = (role_slug or "").strip()
    if slug:
        role = InterviewRole.objects.filter(slug=slug).first()
        if role is None:
            raise InterviewRoleNotFound("This role does not have a prepared interview.")
        return role

    parts = [job_position or ""]
    if job is not None:
        parts.append(getattr(job, "title", "") or "")
        skills = getattr(job, "skills_required", None) or []
        if isinstance(skills, list):
            parts.extend(str(skill) for skill in skills if skill)
    matched = match_role_slug(" ".join(part for part in parts if part))
    if matched is None:
        raise InterviewRoleNotFound(
            "No prepared interview questions are available for this role."
        )
    role = InterviewRole.objects.filter(slug=matched).first()
    if role is None:
        raise InterviewRoleNotFound(
            "No prepared interview questions are available for this role."
        )
    return role


def display_title_for_slug(slug: str) -> str:
    return _TITLES.get(slug, slug)
