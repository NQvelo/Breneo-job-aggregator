from django.core.management.base import BaseCommand
from jobs import fetchers
from jobs.models import Job
from jobs.utils import parse_date
import logging

logger = logging.getLogger(__name__)


# Example companies list (customize for your needs)
COMPANIES = [
    {"name": "Khan Academy", "platform": "greenhouse", "handle": "khan-academy", "logo": ""},
    {"name": "Medium", "platform": "greenhouse", "handle": "medium", "logo": ""},
    {"name": "Spotify", "platform": "lever", "handle": "spotify", "logo": ""},
    {"name": "Snapchat", "platform": "lever", "handle": "snapchat", "logo": ""},
    {"name": "Example Corp Careers", "platform": "career_page", "url": "https://example.com/careers", "logo": ""},
]

PLATFORM_TO_FETCHER = {
    "greenhouse": fetchers.fetch_greenhouse,
    "lever": fetchers.fetch_lever,
    "workable": fetchers.fetch_workable,
    "smartrecruiters": fetchers.fetch_smartrecruiters if hasattr(fetchers, "fetch_smartrecruiters") else None,
    "rss": fetchers.fetch_rss,
    "jobs.ge": fetchers.fetch_jobs_ge_listings,
    "career_page": fetchers.fetch_generic_career_page,
}


class Command(BaseCommand):
    help = "Fetch jobs from configured companies and store/update in DB"

    def handle(self, *args, **options):
        total = 0
        for comp in COMPANIES:
            platform = comp.get("platform")
            company_name = comp.get("name")
            logger.info("Fetching for %s (%s)", company_name, platform)
            fetcher = PLATFORM_TO_FETCHER.get(platform)
            if not fetcher:
                logger.warning("No fetcher for platform: %s", platform)
                continue

            # call fetcher with appropriate args
            if platform in ("greenhouse", "lever", "workable", "smartrecruiters"):
                jobs_data = fetcher(comp.get("handle"), company_name, comp.get("logo"))
            else:
                # rss, jobs.ge, career_page expect a URL
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
                    }

                    obj, created = Job.objects.update_or_create(
                        platform=platform,
                        external_job_id=ext_id,
                        defaults=defaults,
                    )
                    total += 1
                except Exception:
                    logger.exception("Failed to save job: %s", j.get("title"))

            # mark jobs for this company/platform inactive if they were not found in this fetch
            try:
                qs = Job.objects.filter(platform=platform, company=company_name)
                if found_ids:
                    qs.exclude(external_job_id__in=found_ids).update(is_active=False)
            except Exception:
                logger.exception("Failed to mark inactive jobs for %s (%s)", company_name, platform)

        logger.info("Fetched/updated %d jobs", total)
