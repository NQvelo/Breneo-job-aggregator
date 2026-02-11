from django.core.management.base import BaseCommand

from jobs.models import Job
from jobs.industry_taxonomy import determine_industry_tags


class Command(BaseCommand):
    help = "Backfill industry_tags for the most recent jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Number of most recent jobs to update (default: 50). Use with --all to ignore.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Update every job in the table (no limit).",
        )

    def handle(self, *args, **options):
        qs = Job.objects.order_by("-fetched_at")
        if not options.get("all"):
            qs = qs[: options["limit"]]

        updated = 0
        for job in qs:
            source_industry = None
            if isinstance(job.raw, dict):
                source_industry = (
                    job.raw.get("industry")
                    or job.raw.get("category")
                    or job.raw.get("sector")
                )
            company = job.company
            if company and getattr(company, "additional_details", None) and isinstance(company.additional_details, dict):
                source_industry = (
                    source_industry
                    or company.additional_details.get("industry")
                    or company.additional_details.get("sector")
                )

            tags_str, _ = determine_industry_tags(
                company_name=company.name if company else "",
                job_title=job.title or "",
                source_industry=source_industry,
            )
            # If derived non-empty: overwrite. If derived empty and existing set: keep existing.
            if tags_str:
                job.industry_tags = tags_str
                job.save(update_fields=["industry_tags"])
                updated += 1
            elif not (job.industry_tags or "").strip():
                job.industry_tags = ""
                job.save(update_fields=["industry_tags"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Updated industry_tags for {updated} job(s).")
        )

