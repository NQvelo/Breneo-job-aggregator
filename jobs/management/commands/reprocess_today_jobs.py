"""
Reprocess job description parsing for jobs fetched today.
Replaces existing parsed data (responsibilities, qualifications, summary, benefits)
with freshly parsed values from the raw description.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import Job
from jobs.job_posting_parser import parse_job_posting_for_db
from jobs.utils import process_job_description


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
                    job.benefits = processed.get("benefits") or ""
                    if isinstance(job.structured_description, dict):
                        job.structured_description.update({
                            "company_overview": processed.get("company_overview"),
                            "role_description": processed.get("role_description"),
                        })

                job.save(
                    update_fields=[
                        "responsibilities",
                        "qualifications",
                        "workplace_type",
                        "skills_required",
                        "benefits",
                        "structured_description",
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
