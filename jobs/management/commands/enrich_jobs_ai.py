import logging
import os
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand

from jobs.ai_job_enrichment import (
    AI_FIELDS,
    AIQuotaExhausted,
    ai_enrichment_enabled,
    apply_ai_result,
    current_ai_result,
    reset_provider_state,
    summarize_job_with_ai,
)
from jobs.models import Job

logger = logging.getLogger(__name__)

# Stop the run when calls keep failing (bad key, model removed) instead of trying every job.
MAX_CONSECUTIVE_FAILURES = 10


class Command(BaseCommand):
    help = (
        "Summarize fetched job postings with AI (Groq free models, then Gemini): summary, "
        "responsibilities, qualifications, skills and tools. Only jobs without a summary for their "
        "current text are sent; the run stops when the free daily quotas are used up."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=int(os.environ.get("AI_ENRICH_MAX_PER_RUN", "1500")),
            help="Maximum jobs to send in this run (newest first). Env: AI_ENRICH_MAX_PER_RUN.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=int(os.environ.get("AI_ENRICH_WORKERS", "3")),
            help="Parallel requests. Env: AI_ENRICH_WORKERS.",
        )
        parser.add_argument("--platform", help="Only jobs from this platform (e.g. jobs.ge).")
        parser.add_argument("--force", action="store_true", help="Regenerate even when a current summary exists.")

    def handle(self, *args, **options):
        if not ai_enrichment_enabled():
            self.stdout.write(self.style.WARNING(
                "Neither GROQ_API_KEY nor GEMINI_API_KEY is set; skipping AI job summaries."
            ))
            return
        reset_provider_state()

        qs = (
            Job.objects.filter(is_active=True)
            .exclude(platform="employer")
            .exclude(description__isnull=True)
            .exclude(description="")
            .order_by("-posted_at", "-id")
        )
        if options.get("platform"):
            qs = qs.filter(platform=options["platform"])

        limit = max(0, options["limit"])
        pending = []
        for job in qs.iterator(chunk_size=500):
            if options["force"] or current_ai_result(job) is None:
                pending.append(job)
                if len(pending) >= limit:
                    break

        self.stdout.write(f"AI summaries: {len(pending)} job(s) to process")
        done = failed = consecutive_failures = 0
        models: dict[str, int] = {}
        stop_reason = None
        pool = ThreadPoolExecutor(max_workers=max(1, options["workers"]))
        try:
            futures = [pool.submit(summarize_job_with_ai, j.title, j.description) for j in pending]
            for job, future in zip(pending, futures):
                try:
                    result = future.result()
                except AIQuotaExhausted:
                    stop_reason = "free AI quota used up for today; the rest are done on the next run"
                    break
                if result is None:
                    failed += 1
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        stop_reason = f"{consecutive_failures} calls failed in a row (check API keys / models)"
                        break
                    continue
                consecutive_failures = 0
                model = result.get("_model") or "unknown"
                models[model] = models.get(model, 0) + 1
                apply_ai_result(job, result)
                Job.objects.filter(pk=job.pk).update(**{f: getattr(job, f) for f in AI_FIELDS})
                done += 1
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

        if stop_reason:
            self.stdout.write(self.style.WARNING(f"  ⊘ Stopped: {stop_reason}"))
        by_model = ", ".join(f"{m}: {n}" for m, n in sorted(models.items())) or "none"
        self.stdout.write(self.style.SUCCESS(
            f"  ✓ Summarized {done} job(s), {failed} failed, {len(pending) - done - failed} left (by model: {by_model})"
        ))
