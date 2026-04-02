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


def get_employer_job_or_none(job_id: int) -> Job | None:
    return Job.objects.filter(id=job_id, platform="employer").select_related("company").first()


def update_employer_job(job: Job, payload: dict[str, Any]) -> Job:
    company_name = payload.get("company")
    if company_name is not None:
        company_name = str(company_name).strip()
        if not company_name:
            raise ValueError("company_name cannot be empty")
        company, _ = Company.objects.get_or_create(
            name=company_name,
            defaults={"platform": "employer"},
        )
        job.company = company

    if "title" in payload:
        job.title = (payload.get("title") or "").strip()
    if "location" in payload:
        job.location = (payload.get("location") or "").strip() or None
    if "apply_url" in payload:
        job.apply_url = payload.get("apply_url") or None
    if "salary" in payload:
        job.salary = (payload.get("salary") or "").strip() or None
    if "is_active" in payload:
        job.is_active = bool(payload.get("is_active"))

    wm = None
    wt_display = None
    if "work_mode" in payload:
        wm, wt_display = _normalize_work_mode(str(payload.get("work_mode") or ""))
        job.work_mode = wm
        if wt_display:
            job.workplace_type = wt_display

    if "full_description" in payload:
        full_description = (payload.get("full_description") or "").strip()
        job.description = full_description

    raw = job.raw if isinstance(job.raw, dict) else {}
    submitted = raw.get("employer_submitted") if isinstance(raw.get("employer_submitted"), dict) else {}
    submitted["title"] = job.title
    submitted["company"] = job.company.name
    submitted["location"] = job.location or ""
    submitted["work_mode"] = wm or job.work_mode
    submitted["workplace_type"] = job.workplace_type or None
    submitted["apply_url"] = job.apply_url
    submitted["is_active"] = job.is_active
    submitted["salary"] = job.salary or ""
    submitted["full_description"] = job.description or ""
    raw["source"] = "employer"
    raw["employer_submitted"] = submitted
    raw["body"] = job.description or ""
    job.raw = raw

    job.save()
    return job
