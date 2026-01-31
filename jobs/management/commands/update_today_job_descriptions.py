"""
Update today's jobs only with the new short/summarized description.

Runs the job posting parser to build the summary and saves it to
structured_description['summary'], so get_description_short() shows the new description (max 4 lines).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import Job
from jobs.job_posting_parser import parse_job_posting_for_db


class Command(BaseCommand):
    help = "Update today's jobs with new short/summarized description (parsed summary, ~4 lines)"

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
        self.stdout.write(f"Updating description (summary) for {total} job(s) with {date_field} today ({today})...")

        updated = 0
        errors = 0

        for job in jobs:
            try:
                parsed = parse_job_posting_for_db(job.description, location=job.location or "")
                summary = parsed.get("job_description_summary") or ""

                if not job.structured_description:
                    job.structured_description = {}
                if isinstance(job.structured_description, dict):
                    job.structured_description["summary"] = summary
                    job.save(update_fields=["structured_description"])
                    updated += 1
                    self.stdout.write(f"  ✓ {job.title} @ {job.company.name}")
                else:
                    self.stdout.write(self.style.WARNING(f"  ⊘ {job.title}: structured_description not a dict"))

            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  ✗ {job.title} @ {job.company.name}: {e}"))

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Updated {updated} job(s), {errors} error(s).")
        )
