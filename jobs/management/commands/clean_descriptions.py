from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.fetchers import clean_html_to_text
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Clean HTML tags from all existing job descriptions in the database"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually updating',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        jobs = Job.objects.all()
        total = jobs.count()
        updated = 0
        
        self.stdout.write(f"Found {total} jobs to check")
        
        for job in jobs:
            if not job.description:
                continue
                
            # Check if description contains HTML
            if '<' in job.description and '>' in job.description:
                cleaned = clean_html_to_text(job.description)
                
                if cleaned != job.description:
                    if dry_run:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Would clean job {job.id}: {job.title[:50]}..."
                            )
                        )
                    else:
                        job.description = cleaned
                        job.save(update_fields=['description'])
                        updated += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Cleaned job {job.id}: {job.title[:50]}..."
                            )
                        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDry run complete. Would update {updated} jobs."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Updated {updated} job descriptions with clean plain text."
                )
            )
