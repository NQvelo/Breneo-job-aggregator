"""
Re-run job posting parser on all active jobs (strips pay/ITAR/education tails, refreshes
responsibilities, qualifications, summary, matching fields). Clears invalid benefits.
"""
from django.core.management.base import BaseCommand

from jobs.models import Job
from jobs.job_posting_parser import parse_job_posting_for_db
from jobs.utils import process_job_description, is_valid_benefits_text
from jobs.job_normalizer import normalize_job_fields
from jobs.matching_normalizer import extract_visa_sponsorship, extract_work_authorization_required


class Command(BaseCommand):
    help = "Re-parse responsibilities, qualifications, and summary for active jobs; clear junk benefits"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max number of jobs to process",
        )

    def handle(self, *args, **options):
        limit = options.get("limit")
        qs = (
            Job.objects.filter(is_active=True)
            .exclude(description__isnull=True)
            .exclude(description="")
            .order_by("id")
        )
        if limit:
            qs = qs[:limit]
        total = qs.count()
        self.stdout.write(f"Re-parsing {total} job(s)...")

        ok = 0
        err = 0
        for job in qs.iterator():
            try:
                parsed = parse_job_posting_for_db(job.description, location=job.location or "")
                job.responsibilities = parsed.get("responsibilities") or ""
                job.qualifications = parsed.get("qualifications") or ""
                if not job.structured_description:
                    job.structured_description = {}
                if isinstance(job.structured_description, dict):
                    job.structured_description["summary"] = parsed.get("job_description_summary") or ""

                job.workplace_type = parsed.get("workplace_type") or job.workplace_type
                job.skills_required = parsed.get("skills_required") or job.skills_required

                processed = process_job_description(job.description)
                if processed:
                    b = processed.get("benefits") or ""
                    job.benefits = b if (b and is_valid_benefits_text(b)) else ""
                    if isinstance(job.structured_description, dict):
                        job.structured_description.update(
                            {
                                "company_overview": processed.get("company_overview"),
                                "role_description": processed.get("role_description"),
                            }
                        )

                norm = normalize_job_fields(
                    title=job.title,
                    description_raw=job.description,
                    location=job.location,
                    qualifications_text=job.qualifications,
                )
                job.work_mode = norm.get("work_mode", "unknown")
                job.seniority = norm.get("seniority", "unknown")
                job.role_category = norm.get("role_category")
                job.min_years_experience = norm.get("min_years_experience")
                job.skills_required = norm.get("skills_required") or []
                job.skills_preferred = norm.get("skills_preferred") or []
                job.tech_stack = norm.get("tech_stack") or []
                job.tech_stack_candidates = norm.get("tech_stack_candidates") or []
                job.languages_required = norm.get("languages_required") or []
                job.embedding_text = norm.get("embedding_text")
                job.data_completeness_score = norm.get("data_completeness_score", 0)
                job.location_country = norm.get("location_country")
                job.visa_sponsorship = extract_visa_sponsorship(job.description) or "unknown"
                job.work_authorization_required = extract_work_authorization_required(job.description) or "unknown"

                # Full save so Job.save() hooks stay consistent with the rest of the app
                job.save()
                ok += 1
                if ok % 100 == 0:
                    self.stdout.write(f"  … {ok} done")
            except Exception as e:
                err += 1
                self.stdout.write(self.style.ERROR(f"  ✗ id={job.id}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Done. Updated {ok} job(s), {err} error(s)."))
