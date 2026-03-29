"""
Delete the oldest N jobs by fetched_at (then id). Use to trim stale rows.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import Job


class Command(BaseCommand):
    help = "Delete the oldest jobs by fetched_at (stalest rows first)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=1000,
            help="Number of jobs to delete (default: 1000)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many would be deleted without deleting",
        )

    def handle(self, *args, **options):
        n = max(1, options["count"])
        dry = options["dry_run"]

        qs = Job.objects.order_by("fetched_at", "id")[:n]
        ids = list(qs.values_list("id", flat=True))
        total = len(ids)

        if dry:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: would delete {total} job(s) (oldest by fetched_at).")
            )
            return

        with transaction.atomic():
            deleted, by_kind = Job.objects.filter(id__in=ids).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {total} job(s). Job rows removed: {by_kind.get('jobs.Job', total)}."
            )
        )
