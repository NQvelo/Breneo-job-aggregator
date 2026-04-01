"""Create employer-posted jobs: same enrichment pipeline as fetched jobs."""
from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone

from .models import Company, Job, WORK_MODE_CHOICES


def _normalize_work_mode(work_mode: str) -> tuple[str, str]:
    """
    Map user input to (work_mode, workplace_type display string).
    workplace_type matches Remote / Hybrid / On-site used elsewhere.
    """
    key = (work_mode or "").strip().lower().replace(" ", "_").replace("-", "_")
    mapping: dict[str, tuple[str, str]] = {
        "remote": ("remote", "Remote"),
        "hybrid": ("hybrid", "Hybrid"),
        "onsite": ("onsite", "On-site"),
        "on_site": ("onsite", "On-site"),
        "unknown": ("unknown", ""),
    }
    if key in mapping:
        return mapping[key]
    valid = {c[0] for c in WORK_MODE_CHOICES}
    if key in valid:
        return key, ""
    return "unknown", ""


def create_employer_job(
    *,
    title: str,
    company_name: str,
    location: str,
    work_mode: str,
    full_description: str,
    salary: str = "",
    apply_url: str | None = None,
    is_active: bool = True,
) -> Job:
    """
    Persist full_description in Job.description (enrichment) and in raw (employer payload + body).
    Job.save() runs parsing, structured_description, and normalizers like fetched jobs.
    """
    wm, wt_display = _normalize_work_mode(work_mode)
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("company_name is required")

    company, _ = Company.objects.get_or_create(
        name=company_name,
        defaults={"platform": "employer"},
    )

    external_job_id = f"employer-{uuid.uuid4().hex}"

    raw: dict[str, Any] = {
        "source": "employer",
        "employer_submitted": {
            "title": title.strip(),
            "company": company_name,
            "location": (location or "").strip(),
            "work_mode": wm,
            "workplace_type": wt_display or None,
            "apply_url": apply_url or None,
            "is_active": is_active,
            "salary": (salary or "").strip(),
            "full_description": full_description or "",
        },
        "body": full_description or "",
    }

    job = Job(
        title=title.strip(),
        company=company,
        location=(location or "").strip() or None,
        description=(full_description or "").strip(),
        apply_url=apply_url or None,
        platform="employer",
        external_job_id=external_job_id,
        is_active=is_active,
        posted_at=timezone.now(),
        raw=raw,
        salary=(salary or "").strip() or None,
    )
    job.save()
    return job
