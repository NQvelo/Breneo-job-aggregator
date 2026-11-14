from django.core.management.base import BaseCommand

from jobs.user_match_store import refresh_all_stored_profiles


class Command(BaseCommand):
    help = (
        "Re-score stored user snapshots against today's jobs and append new matches. "
        "Older matches are kept. Run after fetch_jobs / enrich_jobs_ai on the daily cron."
    )

    def handle(self, *args, **options):
        count = refresh_all_stored_profiles()
        self.stdout.write(self.style.SUCCESS(f"Refreshed matches for {count} user snapshot(s)."))
