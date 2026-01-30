from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.utils import process_job_description
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Reprocess all job descriptions using Hugging Face AI to update responsibilities and qualifications"

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of jobs to reprocess',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Reprocess even if fields already exist',
        )
        parser.add_argument(
            '--job-id',
            type=int,
            help='Process a specific job ID',
        )

    def handle(self, *args, **options):
        limit = options.get('limit')
        force = options.get('force')
        job_id = options.get('job_id')

        if job_id:
            jobs = Job.objects.filter(id=job_id)
        else:
            jobs = Job.objects.filter(is_active=True).exclude(description='')
            if not force:
                # Only process jobs missing some info if not forced
                from django.db.models import Q
                jobs = jobs.filter(
                    Q(responsibilities__isnull=True) | 
                    Q(qualifications__isnull=True) |
                    Q(responsibilities='') |
                    Q(qualifications='')
                )
            
            if limit:
                jobs = jobs[:limit]

        total = jobs.count()
        self.stdout.write(f"Starting to reprocess {total} jobs...")

        success_count = 0
        fail_count = 0

        for i, job in enumerate(jobs):
            self.stdout.write(f"[{i+1}/{total}] Processing: {job.title} @ {job.company.name} (ID: {job.id})")
            
            try:
                # Use the new Hugging Face powered function
                result = process_job_description(job.description)
                
                if result:
                    # Update fields
                    if result.get('responsibilities'):
                        job.responsibilities = result['responsibilities']
                    if result.get('qualifications'):
                        job.qualifications = result['qualifications']
                    if result.get('benefits'):
                        job.benefits = result.get('benefits')
                    
                    # Store other structured data
                    if not job.structured_description:
                        job.structured_description = {}
                    
                    job.structured_description.update({
                        'summary': result.get('summary'),
                        'company_overview': result.get('company_overview'),
                        'role_description': result.get('role_description'),
                    })
                    
                    job.save()
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Successfully updated."))
                else:
                    fail_count += 1
                    self.stdout.write(self.style.WARNING(f"  ✗ AI processing failed to return results."))
                
                # Small delay to avoid hitting rate limits too fast (if any)
                time.sleep(0.5)

            except Exception as e:
                fail_count += 1
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
                logger.exception(f"Failed to process job {job.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"\nDone! Processed {total} jobs: {success_count} succeeded, {fail_count} failed."))
