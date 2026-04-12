from django.core.management.base import BaseCommand

from jobs.models import Job
from jobs.job_normalizer import parse_stored_location_fields


class Command(BaseCommand):
    help = (
        "Backfill Job.location (city) and Job.location_country from parse_stored_location_fields, "
        "same rules as fetch (e.g. semicolon-separated US offices → first city + USA)."
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

            ploc, pcountry = parse_stored_location_fields(job.location)
            orig_loc = job.location
            orig_ctry = job.location_country

            new_loc = orig_loc
            new_ctry = orig_ctry
            if ploc is not None and ploc != (orig_loc or "").strip():
                new_loc = ploc
            if pcountry is not None and pcountry != (orig_ctry or ""):
                new_ctry = pcountry

            if new_loc == orig_loc and new_ctry == orig_ctry:
                continue

            would_change += 1
            if dry_run:
                continue

            job.location = new_loc
            job.location_country = new_ctry
            batch.append(job)
            if len(batch) >= batch_size:
                Job.objects.bulk_update(batch, ["location", "location_country"])
                saved += len(batch)
                batch = []

        if not dry_run and batch:
            Job.objects.bulk_update(batch, ["location", "location_country"])
            saved += len(batch)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"Dry run: {would_change} job(s) would be updated.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Updated {saved} job(s) ({would_change} needed changes).")
            )
