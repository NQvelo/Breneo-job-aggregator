from django.core.management.base import BaseCommand
from django.db import models
from jobs.models import Job
from jobs.utils import process_job_description
from jobs.job_posting_parser import extract_workplace_type_and_skills
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process job descriptions to extract responsibilities, qualifications, benefits, workplace_type, and skills_required"

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Process all jobs, even if they already have extracted fields',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of jobs to process',
        )

    def handle(self, *args, **options):
        # Find jobs that need processing
        if options['all']:
            jobs = Job.objects.filter(description__isnull=False).exclude(description='')
        else:
            # Only process jobs missing key fields
            jobs = Job.objects.filter(
                description__isnull=False
            ).exclude(
                description=''
            ).filter(
                models.Q(responsibilities__isnull=True) |
                models.Q(responsibilities='') |
                models.Q(qualifications__isnull=True) |
                models.Q(qualifications='') |
                models.Q(benefits__isnull=True) |
                models.Q(workplace_type__isnull=True) |
                models.Q(workplace_type='') |
                models.Q(skills_required=[]) |
                models.Q(skills_required__isnull=True)
            )
        
        if options['limit']:
            jobs = jobs[:options['limit']]
        
        total = jobs.count()
        self.stdout.write(f"Processing {total} job(s)...")
        
        processed = 0
        errors = 0
        
        for job in jobs:
            try:
                if not job.description:
                    continue

                updated = False
                # Process job description (utils)
                processed_data = process_job_description(job.description)

                if processed_data:
                    if processed_data.get('responsibilities'):
                        job.responsibilities = processed_data.get('responsibilities')
                        updated = True
                    if processed_data.get('qualifications'):
                        job.qualifications = processed_data.get('qualifications')
                        updated = True
                    if processed_data.get('benefits'):
                        job.benefits = processed_data.get('benefits')
                        updated = True
                    if not job.structured_description:
                        job.structured_description = {}
                    if isinstance(job.structured_description, dict):
                        job.structured_description.update({
                            'summary': processed_data.get('summary'),
                            'company_overview': processed_data.get('company_overview'),
                            'role_description': processed_data.get('role_description'),
                        })
                        updated = True

                # Extract workplace_type and skills_required
                extracted = extract_workplace_type_and_skills(job.description, job.location or "")
                if extracted.get('workplace_type'):
                    job.workplace_type = extracted['workplace_type']
                    updated = True
                if extracted.get('skills_required'):
                    job.skills_required = extracted['skills_required']
                    updated = True

                if updated:
                    job.save(update_fields=[
                        'responsibilities', 'qualifications',
                        'benefits', 'structured_description',
                        'workplace_type', 'skills_required',
                    ])
                    processed += 1
                    self.stdout.write(f"  ✓ Processed: {job.title} @ {job.company.name}")
                
            except Exception as e:
                errors += 1
                logger.exception(f"Failed to process job {job.id}: {e}")
                self.stdout.write(self.style.ERROR(f"  ✗ Error processing {job.title}: {str(e)}"))
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} job(s), {errors} error(s)"))
