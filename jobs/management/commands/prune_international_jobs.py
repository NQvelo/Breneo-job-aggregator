from django.core.management.base import BaseCommand

from jobs.management.commands.fetch_jobs import hide_disallowed_international_jobs


class Command(BaseCommand):
    help = (
        "Hide stored international jobs whose location is tied to a country other than Georgia "
        "(e.g. 'USA - Remote, TX') or whose role is outside the supported families. No fetching."
    )

    def handle(self, *args, **options):
        hidden = hide_disallowed_international_jobs()
        self.stdout.write(self.style.SUCCESS(f"Hid {hidden} international job(s)"))
