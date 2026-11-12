from django.core.management.base import BaseCommand

from jobs.ai_job_enrichment import ai_jobs_per_day, ai_pending_q
from jobs.models import Job, JobApplication


class Command(BaseCommand):
    help = (
        "Delete fetched jobs still waiting for an AI summary beyond the newest --keep (default: the "
        "AI daily capacity). Deleted jobs are fetched again on later runs, within the daily AI limit. "
        "Jobs with applications are never deleted. Dry run unless --delete is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int, default=None, help="Jobs to keep waiting (default: AI_JOBS_PER_DAY).")
        parser.add_argument("--delete", action="store_true", help="Actually delete (default: only report).")

    def handle(self, *args, **options):
        keep = ai_jobs_per_day() if options["keep"] is None else max(0, options["keep"])
        pending_ids = list(
            Job.objects.filter(ai_pending_q()).order_by("-posted_at", "-id").values_list("id", flat=True)
        )
        excess = pending_ids[keep:]
        with_apps = set(JobApplication.objects.filter(job_id__in=excess).values_list("job_id", flat=True))
        to_delete = [i for i in excess if i not in with_apps]
        self.stdout.write(
            f"{len(pending_ids)} job(s) waiting for an AI summary; keeping the newest {min(keep, len(pending_ids))}, "
            f"{len(to_delete)} to delete ({len(with_apps)} kept because they have applications)"
        )
        if not options["delete"]:
            self.stdout.write("Dry run: pass --delete to delete them.")
            return
        deleted = 0
        for start in range(0, len(to_delete), 500):
            deleted += Job.objects.filter(id__in=to_delete[start:start + 500]).delete()[1].get("jobs.Job", 0)
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} job(s)"))
