from django.core.management.base import BaseCommand

from jobs.models import Job
from jobs.location_resolver import resolve_location


class Command(BaseCommand):
    help = (
        "Backfill Job.location, location_country, and location_region. "
        "Georgia the U.S. state is stored as country USA plus region Georgia."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print how many rows would change without writing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max jobs to scan (default: all).",
        )
        parser.add_argument(
            "--active-only",
            action="store_true",
            help="Only jobs with is_active=True.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        active_only = options["active_only"]

        qs = Job.objects.all().order_by("pk")
        if active_only:
            qs = qs.filter(is_active=True)
        if limit is not None:
            qs = qs[:limit]

        would_change = 0
        batch: list[Job] = []
        batch_size = 500
        saved = 0

        for job in qs.iterator(chunk_size=1000):
            if not job.location or not str(job.location).strip():
                continue

            resolved = resolve_location(
                job.location,
                platform=job.platform,
                context=job.description,
                stored_country=job.location_country,
            )
            orig_loc = job.location
            orig_ctry = job.location_country
            orig_region = job.location_region

            new_loc = orig_loc
            new_ctry = orig_ctry
            new_region = orig_region
            if resolved.country_authoritative:
                if resolved.city is not None and resolved.city != (orig_loc or "").strip():
                    new_loc = resolved.city
                new_ctry = resolved.country
                new_region = resolved.region
            elif resolved.country and resolved.country != (orig_ctry or ""):
                new_ctry = resolved.country

            if new_loc == orig_loc and new_ctry == orig_ctry and new_region == orig_region:
                continue

            would_change += 1
            if dry_run:
                continue

            job.location = new_loc
            job.location_country = new_ctry
            job.location_region = new_region
            batch.append(job)
            if len(batch) >= batch_size:
                Job.objects.bulk_update(batch, ["location", "location_country", "location_region"])
                saved += len(batch)
                batch = []

        if not dry_run and batch:
            Job.objects.bulk_update(batch, ["location", "location_country", "location_region"])
            saved += len(batch)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"Dry run: {would_change} job(s) would be updated.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Updated {saved} job(s) ({would_change} needed changes).")
            )
