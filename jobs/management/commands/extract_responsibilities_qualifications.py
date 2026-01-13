from django.core.management.base import BaseCommand
from django.db import models as django_models
from jobs.models import Job
from jobs.utils import extract_responsibilities_and_qualifications, summarize_text
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Extract responsibilities and qualifications from existing job descriptions using AI"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be extracted without actually updating',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-extract even if fields already exist',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of jobs to process',
        )
        parser.add_argument(
            '--summarize',
            action='store_true',
            default=True,
            help='Summarize extracted responsibilities and qualifications (default: True)',
        )
        parser.add_argument(
            '--no-summarize',
            dest='summarize',
            action='store_false',
            help='Do not summarize extracted text',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        limit = options.get('limit')
        summarize = options.get('summarize', True)
        
        # Get jobs to process
        if force:
            jobs = Job.objects.filter(description__isnull=False).exclude(description='')
        else:
            jobs = Job.objects.filter(
                description__isnull=False
            ).exclude(
                description=''
            ).filter(
                django_models.Q(responsibilities__isnull=True) | 
                django_models.Q(responsibilities='') |
                django_models.Q(qualifications__isnull=True) | 
                django_models.Q(qualifications='')
            )
        
        if limit:
            jobs = jobs[:limit]
        
        total = jobs.count()
        updated = 0
        errors = 0
        
        self.stdout.write(f"Found {total} jobs to process")
        
        for job in jobs:
            try:
                if not job.description:
                    continue
                
                # Extract and optionally summarize
                responsibilities, qualifications = extract_responsibilities_and_qualifications(
                    job.description, 
                    summarize=summarize
                )
                
                # If not summarizing during extraction, summarize existing long text
                if not summarize:
                    if responsibilities and len(responsibilities) > 300:
                        responsibilities = summarize_text(responsibilities, max_length=200, min_length=50)
                    if qualifications and len(qualifications) > 300:
                        qualifications = summarize_text(qualifications, max_length=200, min_length=50)
                
                if dry_run:
                    if responsibilities or qualifications:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Would extract for job {job.id}: {job.title[:50]}..."
                            )
                        )
                        if responsibilities:
                            self.stdout.write(f"  Responsibilities: {responsibilities[:100]}...")
                        if qualifications:
                            self.stdout.write(f"  Qualifications: {qualifications[:100]}...")
                else:
                    updated_fields = []
                    if responsibilities and (not job.responsibilities or force):
                        job.responsibilities = responsibilities
                        updated_fields.append("responsibilities")
                    if qualifications and (not job.qualifications or force):
                        job.qualifications = qualifications
                        updated_fields.append("qualifications")
                    
                    if updated_fields:
                        job.save(update_fields=updated_fields)
                        updated += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Updated job {job.id}: {job.title[:50]}... ({', '.join(updated_fields)})"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"⊘ No extraction for job {job.id}: {job.title[:50]}..."
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
                    f"\n✓ Updated {updated} jobs. {errors} errors."
                )
            )
