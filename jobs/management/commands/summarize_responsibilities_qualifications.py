from django.core.management.base import BaseCommand
from django.db import models as django_models
from jobs.models import Job
from jobs.utils import summarize_text
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Summarize existing responsibilities and qualifications fields using AI"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be summarized without actually updating',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-summarize even if text is already short',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of jobs to process',
        )
        parser.add_argument(
            '--min-length',
            type=int,
            default=300,
            help='Minimum length of text to summarize (default: 300)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        limit = options.get('limit')
        min_length = options.get('min_length', 300)
        
        # Get jobs with long responsibilities or qualifications
        jobs = Job.objects.filter(
            django_models.Q(responsibilities__isnull=False) | 
            django_models.Q(qualifications__isnull=False)
        ).exclude(
            responsibilities='',
            qualifications=''
        )
        
        if limit:
            jobs = jobs[:limit]
        
        total = jobs.count()
        updated = 0
        errors = 0
        
        self.stdout.write(f"Found {total} jobs to check for summarization")
        
        for job in jobs:
            try:
                updated_fields = []
                
                # Summarize responsibilities if needed
                if job.responsibilities:
                    should_summarize = force or len(job.responsibilities) > min_length
                    if should_summarize:
                        summarized = summarize_text(
                            job.responsibilities, 
                            max_length=200, 
                            min_length=50
                        )
                        if summarized and summarized != job.responsibilities:
                            if dry_run:
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"Would summarize responsibilities for job {job.id}: {job.title[:50]}..."
                                    )
                                )
                                self.stdout.write(f"  Original length: {len(job.responsibilities)}")
                                self.stdout.write(f"  Summary length: {len(summarized)}")
                            else:
                                job.responsibilities = summarized
                                updated_fields.append("responsibilities")
                
                # Summarize qualifications if needed
                if job.qualifications:
                    should_summarize = force or len(job.qualifications) > min_length
                    if should_summarize:
                        summarized = summarize_text(
                            job.qualifications, 
                            max_length=200, 
                            min_length=50
                        )
                        if summarized and summarized != job.qualifications:
                            if dry_run:
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"Would summarize qualifications for job {job.id}: {job.title[:50]}..."
                                    )
                                )
                                self.stdout.write(f"  Original length: {len(job.qualifications)}")
                                self.stdout.write(f"  Summary length: {len(summarized)}")
                            else:
                                job.qualifications = summarized
                                updated_fields.append("qualifications")
                
                if updated_fields:
                    if not dry_run:
                        job.save(update_fields=updated_fields)
                        updated += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Summarized job {job.id}: {job.title[:50]}... ({', '.join(updated_fields)})"
                            )
                        )
                        
            except Exception as e:
                errors += 1
                logger.exception(f"Error processing job {job.id}: {e}")
                self.stdout.write(
                    self.style.ERROR(
                        f"✗ Error processing job {job.id}: {str(e)}"
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
                    f"\n✓ Summarized {updated} jobs. {errors} errors."
                )
            )
