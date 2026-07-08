"""Build LLM context from a jobs.Job posting for tailored interview questions."""

from __future__ import annotations

from dataclasses import dataclass

from jobs.models import Job


@dataclass(frozen=True)
class InterviewJobContext:
    job_position: str
    company_name: str = ""
    seniority: str = ""
    role_category: str = ""
    workplace_type: str = ""
    skills_required: tuple[str, ...] = ()
    skills_preferred: tuple[str, ...] = ()
    tech_stack: tuple[str, ...] = ()
    qualifications: str = ""
    responsibilities: str = ""
    job_id: int | None = None

    @classmethod
    def from_job(cls, job: Job) -> InterviewJobContext:
        company_name = job.company.name if job.company_id else ""
        return cls(
            job_position=(job.title or "").strip(),
            company_name=company_name.strip(),
            seniority=(job.seniority or "").strip(),
            role_category=(job.role_category or "").strip(),
            workplace_type=(job.workplace_type or job.work_mode or "").strip(),
            skills_required=tuple(job.skills_required or []),
            skills_preferred=tuple(job.skills_preferred or []),
            tech_stack=tuple(job.tech_stack or []),
            qualifications=(job.qualifications or "").strip(),
            responsibilities=(job.responsibilities or "").strip(),
            job_id=job.pk,
        )

    @classmethod
    def from_position(cls, job_position: str) -> InterviewJobContext:
        return cls(job_position=job_position.strip())


def format_job_context_for_llm(context: InterviewJobContext) -> str:
    """Serialize job context for the question-generation LLM prompt."""
    lines = [f"job_position: {context.job_position}"]
    if context.job_id is not None:
        lines.append(f"job_id: {context.job_id}")
    if context.company_name:
        lines.append(f"company_name: {context.company_name}")
    if context.seniority:
        lines.append(f"seniority: {context.seniority}")
    if context.role_category:
        lines.append(f"role_category: {context.role_category}")
    if context.workplace_type:
        lines.append(f"workplace_type: {context.workplace_type}")
    if context.skills_required:
        lines.append(f"skills_required: {', '.join(context.skills_required)}")
    if context.skills_preferred:
        lines.append(f"skills_preferred: {', '.join(context.skills_preferred)}")
    if context.tech_stack:
        lines.append(f"tech_stack: {', '.join(context.tech_stack)}")
    if context.qualifications:
        lines.append(f"qualifications:\n{context.qualifications}")
    if context.responsibilities:
        lines.append(f"responsibilities:\n{context.responsibilities}")
    return "\n".join(lines)
