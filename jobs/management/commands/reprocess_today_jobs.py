"""
Reprocess job description parsing for jobs fetched today.
Replaces existing parsed data (responsibilities, qualifications, summary, benefits)
and populates matching fields (work_mode, seniority, role_category, skills_required,
skills_preferred, tech_stack, etc.) from the job normalizer.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import Job
from jobs.job_posting_parser import parse_job_posting_for_db
from jobs.utils import process_job_description, is_valid_benefits_text
from jobs.job_normalizer import normalize_job_fields
from jobs.matching_normalizer import extract_visa_sponsorship, extract_work_authorization_required


class Command(BaseCommand):
    help = "Reprocess job description parsing for today's jobs only; replace old parsed data with new"

    def add_arguments(self, parser):
        parser.add_argument(
            "--posted",
            action="store_true",
            help="Filter by posted_at date instead of fetched_at",
        )

    def handle(self, *args, **options):
        today = timezone.now().date()

        if options["posted"]:
            jobs = Job.objects.filter(
                is_active=True,
                posted_at__date=today,
                description__isnull=False,
            ).exclude(description="")
            date_field = "posted_at"
        else:
            jobs = Job.objects.filter(
                is_active=True,
                fetched_at__date=today,
                description__isnull=False,
            ).exclude(description="")
            date_field = "fetched_at"

        total = jobs.count()
        self.stdout.write(f"Reprocessing {total} job(s) with {date_field} today ({today})...")

        updated = 0
        errors = 0

        for job in jobs:
            try:
                # 1) Job posting parser (responsibilities, qualifications, summary, workplace_type, skills_required)
                parsed = parse_job_posting_for_db(job.description, location=job.location or "")

                job.responsibilities = parsed.get("responsibilities") or ""
                job.qualifications = parsed.get("qualifications") or ""
                job.workplace_type = parsed.get("workplace_type") or job.workplace_type
                job.skills_required = parsed.get("skills_required") or []

                if not job.structured_description:
                    job.structured_description = {}
                if isinstance(job.structured_description, dict):
                    job.structured_description["summary"] = parsed.get(
                        "job_description_summary"
                    ) or ""

                # 2) Utils processor (benefits, company_overview, role_description)
                processed = process_job_description(job.description)
                if processed:
                    b = processed.get("benefits") or ""
                    job.benefits = b if (b and is_valid_benefits_text(b)) else ""
                    if isinstance(job.structured_description, dict):
                        job.structured_description.update({
                            "company_overview": processed.get("company_overview"),
                            "role_description": processed.get("role_description"),
                        })

                # 3) Matching fields (work_mode, seniority, role_category, skills, tech_stack, etc.)
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

                job.save(
                    update_fields=[
                        "responsibilities",
                        "qualifications",
                        "workplace_type",
                        "skills_required",
                        "benefits",
                        "structured_description",
                        "work_mode",
                        "seniority",
                        "role_category",
                        "min_years_experience",
                        "skills_preferred",
                        "tech_stack",
                        "tech_stack_candidates",
                        "languages_required",
                        "embedding_text",
                        "data_completeness_score",
                        "location_country",
                        "visa_sponsorship",
                        "work_authorization_required",
                    ]
                )
                updated += 1
                self.stdout.write(f"  ✓ {job.title} @ {job.company.name}")

            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"  ✗ {job.title} @ {job.company.name}: {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Updated {updated} job(s), {errors} error(s).")
        )
