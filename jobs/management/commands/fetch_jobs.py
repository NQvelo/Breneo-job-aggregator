from django.core.management.base import BaseCommand
from jobs.models import Company, Job
from jobs.utils import parse_date
from jobs import fetchers
import logging

logger = logging.getLogger(__name__)

# Generate logo URL from logo.dev
def get_logo_url(company_name: str, size=101) -> str:
    from jobs.fetchers import LOGO_DEV_PUBLIC_KEY
    safe_name = company_name.replace(" ", "")
    return f"https://img.logo.dev/name/{safe_name}?token={LOGO_DEV_PUBLIC_KEY}&size={size}&retina=true"

# Example companies
COMPANIES = [
    {"name": "Intercom", "platform": "greenhouse", "handle": "intercom"},
    {"name": "Figma", "platform": "greenhouse", "handle": "figma"},
    {"name": "Spotify", "platform": "lever", "handle": "spotify"},
]

# Map platform to fetcher function
PLATFORM_TO_FETCHER = {
    "greenhouse": fetchers.fetch_greenhouse,
    "lever": fetchers.fetch_lever,
    "workable": fetchers.fetch_workable,
    "smartrecruiters": getattr(fetchers, "fetch_smartrecruiters", None),
    "rss": fetchers.fetch_rss,
    "jobs.ge": fetchers.fetch_jobs_ge_listings,
    "career_page": fetchers.fetch_generic_career_page,
    "ashby": fetchers.fetch_ashby,
}

class Command(BaseCommand):
    help = "Fetch jobs from configured companies and store/update in DB"

    def handle(self, *args, **options):
        total = 0
        for comp in COMPANIES:
            platform = comp.get("platform")
            company_name = comp.get("name")
            company_logo = get_logo_url(company_name)

            # Ensure company exists before fetching jobs
            company_obj, created = Company.objects.get_or_create(
                name=company_name,
                defaults={
                    "logo": company_logo,
                    "platform": platform,
                }
            )
            if not company_obj.logo:
                company_obj.logo = company_logo
                company_obj.save()

            logger.info("Fetching jobs for %s (%s)", company_name, platform)

            fetcher = PLATFORM_TO_FETCHER.get(platform)
            if not fetcher:
                logger.warning("No fetcher for platform: %s", platform)
                continue

            if platform in ("greenhouse", "lever", "workable", "smartrecruiters", "ashby"):
                jobs_data = fetcher(comp.get("handle"), company_name)
            else:
                jobs_data = fetcher(comp.get("url") or comp.get("handle"), company_name)

            found_ids = set()
            for j in jobs_data:
                try:
                    ext_id = j.get("external_job_id") or j.get("apply_url")
                    if not ext_id:
                        continue
                    found_ids.add(ext_id)

                    # Create/update Job
                    Job.objects.update_or_create(
                        platform=platform,
                        external_job_id=ext_id,
                        defaults={
                            "title": j.get("title") or "",
                            "company": company_obj,
                            "location": j.get("location"),
                            "description": j.get("description"),
                            "apply_url": j.get("apply_url") or ext_id,
                            "posted_at": parse_date(j.get("posted_at")) if j.get("posted_at") else None,
                            "raw": j.get("raw") or {},
                            "is_active": True,
                            "company_logo": j.get("logo") or company_logo,
                        },
                    )
                    total += 1

                except Exception:
                    logger.exception("Failed to save job: %s", j.get("title"))

            # Mark old jobs inactive
            try:
                qs = Job.objects.filter(platform=platform, company=company_obj)
                if found_ids:
                    qs.exclude(external_job_id__in=found_ids).update(is_active=False)
            except Exception:
                logger.exception("Failed to mark inactive jobs for %s (%s)", company_name, platform)

        logger.info("Total jobs fetched/updated: %d", total)


