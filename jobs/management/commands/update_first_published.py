from django.core.management.base import BaseCommand
from django.utils import timezone
from jobs.models import Job
from jobs.utils import parse_date


class Command(BaseCommand):
    help = "Update posted_at field for all jobs by extracting first_published from raw JSON data"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating',
        )
        parser.add_argument(
            '--platform',
            type=str,
            help='Only update jobs for a specific platform (e.g., greenhouse)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        platform_filter = options.get('platform')
        
        # Build queryset
        jobs = Job.objects.filter(raw__isnull=False)
        if platform_filter:
            jobs = jobs.filter(platform=platform_filter)
        
        total_jobs = jobs.count()
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        self.stdout.write(f'Found {total_jobs} jobs with raw data.')
        if platform_filter:
            self.stdout.write(f'Filtering by platform: {platform_filter}')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        self.stdout.write('Processing jobs...')
        
        for job in jobs.iterator(chunk_size=1000):
            try:
                # Skip if raw is not a dict
                if not isinstance(job.raw, dict):
                    skipped_count += 1
                    continue
                
                # Extract first_published from raw data
                first_published = job.raw.get("first_published")
                if not first_published:
                    skipped_count += 1
                    continue
                
                # Parse the date
                parsed_date = parse_date(first_published)
                if not parsed_date:
                    skipped_count += 1
                    continue
                
                # Check if we need to update (only update if posted_at is None or different)
                if job.posted_at is None or job.posted_at != parsed_date:
                    if not dry_run:
                        job.posted_at = parsed_date
                        job.save(update_fields=['posted_at'])
                    updated_count += 1
                    
                    if updated_count % 100 == 0:
                        self.stdout.write(f'Processed {updated_count} updates...')
                else:
                    skipped_count += 1
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'Error processing job ID {job.id}: {str(e)}')
                )
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Summary:'))
        self.stdout.write(f'  Total jobs processed: {total_jobs}')
        self.stdout.write(f'  Jobs updated: {updated_count}')
        self.stdout.write(f'  Jobs skipped: {skipped_count}')
        self.stdout.write(f'  Errors: {error_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a dry run. No changes were saved.'))
            self.stdout.write(self.style.WARNING('Run without --dry-run to apply changes.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nSuccessfully updated {updated_count} jobs.'))
