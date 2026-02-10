from django.core.management.base import BaseCommand

from jobs.models import Job
from jobs.industry_taxonomy import IndustryContext, determine_industry


class Command(BaseCommand):
    help = "Backfill industry_tags for the most recent jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Number of most recent jobs to update (default: 50).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        qs = Job.objects.order_by("-fetched_at")[:limit]

        updated = 0
        for job in qs:
            # Try to get any source-provided industry from raw/company.additional_details
            source_industry = None
            if isinstance(job.raw, dict):
                # Common keys: industry, category, sector (best effort)
                source_industry = (
                    job.raw.get("industry")
                    or job.raw.get("category")
                    or job.raw.get("sector")
                )

            company = job.company
            if hasattr(company, "additional_details") and isinstance(
                company.additional_details, dict
            ):
                source_industry = (
                    source_industry
                    or company.additional_details.get("industry")
                    or company.additional_details.get("sector")
                )

            ctx = IndustryContext(
                title=job.title or "",
                description_raw=job.description or "",
                company_name=company.name if company else "",
                source_industry_field=source_industry,
            )

            tags = determine_industry(ctx)
            # Join here; Job.save() will normalize formatting again
            job.industry_tags = ", ".join(tags) if tags else ""
            job.save(update_fields=["industry_tags"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Updated industry_tags for {updated} job(s).")
        )

