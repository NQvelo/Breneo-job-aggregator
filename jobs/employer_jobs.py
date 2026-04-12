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
        "source": "employer_manual",
        "employer_submitted": {
            "title": title.strip(),
            "company": company_name,
            "city": (location or "").strip(),
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
    from .gemini_job_parser import maybe_parse_employer_description_with_gemini

    maybe_parse_employer_description_with_gemini(job)
    job.save()
    return job


def get_employer_job_or_none(job_id: int) -> Job | None:
    return (
        Job.objects.filter(id=job_id)
        .select_related("company")
        .prefetch_related("company__industries", "company__staff_memberships")
        .first()
    )


def _clean_str_list(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(x).strip() for x in val if str(x).strip()]


def update_employer_job(job: Job, payload: dict[str, Any]) -> Job:
    prev_desc = (job.description or "").strip()

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
    if "location_country" in payload:
        lc = (payload.get("location_country") or "").strip()
        job.location_country = lc or None
    if "apply_url" in payload:
        job.apply_url = payload.get("apply_url") or None
    if "salary" in payload:
        job.salary = (payload.get("salary") or "").strip() or None
    if "is_active" in payload:
        job.is_active = bool(payload.get("is_active"))
    if "benefits" in payload:
        job.benefits = (payload.get("benefits") or "").strip() or None
    if "industry_tags" in payload:
        job.industry_tags = (payload.get("industry_tags") or "").strip() or None
    if "posted_at" in payload:
        job.posted_at = payload.get("posted_at")
    if "skills_preferred" in payload:
        job.skills_preferred = _clean_str_list(payload.get("skills_preferred"))
    if "seniority" in payload:
        job.seniority = payload.get("seniority") or "unknown"
    if "min_years_experience" in payload:
        job.min_years_experience = payload.get("min_years_experience")
    if "visa_sponsorship" in payload:
        job.visa_sponsorship = payload.get("visa_sponsorship") or "unknown"
    if "work_authorization_required" in payload:
        job.work_authorization_required = payload.get("work_authorization_required") or "unknown"

    wm = None
    wt_display = None
    if "work_mode" in payload:
        wm, wt_display = _normalize_work_mode(str(payload.get("work_mode") or ""))
        job.work_mode = wm
        if wt_display:
            job.workplace_type = wt_display
    if "workplace_type" in payload and "work_mode" not in payload:
        wt = (payload.get("workplace_type") or "").strip()
        job.workplace_type = wt or None

    # Main description: full_description takes precedence over alias `description`
    body_text = None
    if "full_description" in payload:
        body_text = (payload.get("full_description") or "").strip()
    elif "description" in payload:
        body_text = (payload.get("description") or "").strip()

    desc_changed = False
    if body_text is not None:
        new_d = body_text.strip()
        desc_changed = new_d != prev_desc
        job.description = new_d

    if body_text is not None and desc_changed and (job.description or "").strip():
        from .gemini_job_parser import maybe_parse_employer_description_with_gemini

        maybe_parse_employer_description_with_gemini(job)
    else:
        if "responsibilities" in payload:
            job.responsibilities = (payload.get("responsibilities") or "").strip() or None
        if "qualifications" in payload:
            job.qualifications = (payload.get("qualifications") or "").strip() or None
        if "skills_required" in payload:
            job.skills_required = _clean_str_list(payload.get("skills_required"))

    raw = job.raw if isinstance(job.raw, dict) else {}
    submitted = raw.get("employer_submitted") if isinstance(raw.get("employer_submitted"), dict) else {}
    submitted["title"] = job.title
    submitted["company"] = job.company.name
    submitted["city"] = job.location or ""
    if job.location_country:
        submitted["country"] = job.location_country
    else:
        submitted.pop("country", None)
    # Remove legacy keys in case older payloads used them.
    submitted.pop("location", None)
    submitted.pop("location_country", None)
    submitted["work_mode"] = wm or job.work_mode
    submitted["workplace_type"] = job.workplace_type or None
    submitted["apply_url"] = job.apply_url
    submitted["is_active"] = job.is_active
    submitted["salary"] = job.salary or ""
    submitted["full_description"] = job.description or ""
    submitted["benefits"] = job.benefits or ""
    submitted["responsibilities"] = job.responsibilities or ""
    submitted["qualifications"] = job.qualifications or ""
    submitted["industry_tags"] = job.industry_tags or ""
    submitted["posted_at"] = job.posted_at.isoformat() if job.posted_at else None
    submitted["skills_required"] = job.skills_required or []
    submitted["skills_preferred"] = job.skills_preferred or []
    submitted["seniority"] = job.seniority
    submitted["min_years_experience"] = job.min_years_experience
    submitted["visa_sponsorship"] = job.visa_sponsorship
    submitted["work_authorization_required"] = job.work_authorization_required
    raw["source"] = "employer_manual"
    raw["employer_submitted"] = submitted
    raw["body"] = job.description or ""
    job.raw = raw

    job.save()
    return job
