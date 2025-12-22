# jobs/management/commands/update_jobs.py
from django.core.management.base import BaseCommand
from jobs import fetchers
from jobs.models import Job
from jobs.utils import parse_date
import logging
from datetime import timedelta
from django.utils import timezone
import requests

logger = logging.getLogger(__name__)

# Example companies list
COMPANIES = [
    # Greenhouse companies
    {"name": "Help Scout", "platform": "greenhouse", "handle": "helpscout", "logo": ""},
    {"name": "Zapier", "platform": "greenhouse", "handle": "zapier", "logo": ""},
    {"name": "Drift", "platform": "greenhouse", "handle": "drift", "logo": ""},
    {"name": "Intercom", "platform": "greenhouse", "handle": "intercom", "logo": ""},


    # Lever companies
    {"name": "Chipper", "platform": "lever", "handle": "chipper", "logo": ""},
    {"name": "Toggl", "platform": "lever", "handle": "toggl", "logo": ""},
    {"name": "Gusto", "platform": "lever", "handle": "gusto", "logo": ""},
    {"name": "Lattice", "platform": "lever", "handle": "lattice", "logo": ""},
    {"name": "Notion", "platform": "lever", "handle": "notion", "logo": ""},
    {"name": "Spotify", "platform": "lever", "handle": "Spotify", "logo": ""},


    # Workable companies
    {"name": "Typeform", "platform": "workable", "handle": "typeform", "logo": ""},
    {"name": "FrontApp", "platform": "workable", "handle": "frontapp", "logo": ""},
    {"name": "Miro", "platform": "workable", "handle": "miro", "logo": ""},
    {"name": "Doist", "platform": "workable", "handle": "doist", "logo": ""},

]


PLATFORM_TO_FETCHER = {
    "greenhouse": fetchers.fetch_greenhouse,
    "lever": fetchers.fetch_lever,
    "workable": fetchers.fetch_workable,
    "smartrecruiters": fetchers.fetch_smartrecruiters if hasattr(fetchers, "fetch_smartrecruiters") else None,
    "rss": fetchers.fetch_rss,
    "jobs.ge": fetchers.fetch_jobs_ge_listings,
    "career_page": fetchers.fetch_generic_career_page,
    "ashby": fetchers.fetch_ashby,  
    "rss": fetchers.fetch_rss,  # <-- RSS fetcher here

}


class Command(BaseCommand):
    help = "Daily update of jobs: fetch new ones and check weekly for inactive jobs"

    def handle(self, *args, **options):
        total_new = 0
        total_checked = 0

        # === DAILY: fetch new/updated jobs ===
        for comp in COMPANIES:
            platform = comp.get("platform")
            company_name = comp.get("name")
            logger.info("Fetching jobs for %s (%s)", company_name, platform)
            fetcher = PLATFORM_TO_FETCHER.get(platform)
            if not fetcher:
                logger.warning("No fetcher for platform: %s", platform)
                continue

            # call fetcher with proper args
            if platform in ("greenhouse", "lever", "workable", "smartrecruiters"):
                jobs_data = fetcher(comp.get("handle"), company_name, comp.get("logo"))
            else:
                jobs_data = fetcher(comp.get("url") or comp.get("handle"), company_name, comp.get("logo"))

            found_ids = set()
            for j in jobs_data:
                try:
                    ext_id = j.get("external_job_id") or j.get("apply_url")
                    if not ext_id:
                        continue
                    found_ids.add(ext_id)

                    defaults = {
                        "title": j.get("title") or "",
                        "company": j.get("company") or company_name,
                        "location": j.get("location"),
                        "description": j.get("description"),
                        "apply_url": j.get("apply_url") or ext_id,
                        "posted_at": parse_date(j.get("posted_at")) if j.get("posted_at") else None,
                        "raw": j.get("raw") or {},
                        "is_active": True,
                        "company_logo": comp.get("logo"),
                    }

                    Job.objects.update_or_create(
                        platform=platform,
                        external_job_id=ext_id,
                        defaults=defaults,
                    )
                    total_new += 1
                except Exception:
                    logger.exception("Failed to save job: %s", j.get("title"))

            # Mark jobs inactive if not found in this fetch
            try:
                qs = Job.objects.filter(platform=platform, company=company_name)
                if found_ids:
                    qs.exclude(external_job_id__in=found_ids).update(is_active=False)
            except Exception:
                logger.exception("Failed to mark inactive jobs for %s (%s)", company_name, platform)

        # === WEEKLY: check if active jobs are still live ===
        one_week_ago = timezone.now() - timedelta(days=7)
        active_jobs = Job.objects.filter(is_active=True, fetched_at__lte=one_week_ago)
        for job in active_jobs:
            try:
                resp = requests.head(job.apply_url, timeout=5)
                if resp.status_code >= 400:
                    job.is_active = False
                    job.save(update_fields=["is_active", "fetched_at"])
                total_checked += 1
            except requests.RequestException:
                job.is_active = False
                job.save(update_fields=["is_active", "fetched_at"])
                total_checked += 1

        logger.info("Daily fetch complete: %d jobs added/updated", total_new)
        logger.info("Weekly check complete: %d jobs checked for activity", total_checked)
