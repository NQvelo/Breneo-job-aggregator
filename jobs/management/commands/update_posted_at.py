from django.core.management.base import BaseCommand
from django.utils import timezone
from jobs.models import Job


class Command(BaseCommand):
    help = "Update jobs that have posted_at=None to set it to their fetched_at timestamp"

    def handle(self, *args, **options):
        # Find all jobs where posted_at is None
        jobs_without_date = Job.objects.filter(posted_at__isnull=True)
        total = jobs_without_date.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('All jobs already have posted_at set.'))
            return
        
        self.stdout.write(f'Found {total} jobs without posted_at. Updating...')
        
        updated = 0
        for job in jobs_without_date:
            # Use fetched_at as fallback, or current time if fetched_at is also None
            job.posted_at = job.fetched_at if job.fetched_at else timezone.now()
            job.save(update_fields=['posted_at'])
            updated += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated {updated} jobs. All jobs now have posted_at set.'
            )
        )

