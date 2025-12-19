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
    {"name": "Help Scout", "platform": "greenhouse", "handle": "helpscout"},
    {"name": "Zapier", "platform": "greenhouse", "handle": "zapier"},
    {"name": "Drift", "platform": "greenhouse", "handle": "drift"},
    {"name": "Intercom", "platform": "greenhouse", "handle": "intercom"},
    {"name": "Trello", "platform": "greenhouse", "handle": "trello"},
    {"name": "Figma", "platform": "greenhouse", "handle": "figma"},
    {"name": "Notion", "platform": "greenhouse", "handle": "notion"},
    {"name": "Stripe", "platform": "greenhouse", "handle": "stripe"},
    {"name": "Plaid", "platform": "greenhouse", "handle": "plaid"},
    {"name": "Chipper", "platform": "lever", "handle": "chipper"},
    {"name": "Toggl", "platform": "lever", "handle": "toggl"},
    {"name": "Gusto", "platform": "lever", "handle": "gusto"},
    {"name": "Lattice", "platform": "lever", "handle": "lattice"},
    {"name": "Notion", "platform": "lever", "handle": "notion"},
    {"name": "Typeform", "platform": "workable", "handle": "typeform"},
    {"name": "FrontApp", "platform": "workable", "handle": "frontapp"},
    {"name": "Figma", "platform": "workable", "handle": "figma"},
    {"name": "Miro", "platform": "workable", "handle": "miro"},
    {"name": "Doist", "platform": "workable", "handle": "doist"},
    {"name": "Breneo", "platform": "career_page", "url": "https://breneo.app/careers"},
    {"name": "Acme Corp", "platform": "career_page", "url": "https://example.com/careers"},
    {"name": "RemoteOK", "platform": "career_page", "url": "https://remoteok.com/remote-jobs"},
    {"name": "WeWorkRemotely", "platform": "career_page", "url": "https://weworkremotely.com/categories/remote-programming-jobs"},
    {"name": "EuropeRemotely", "platform": "career_page", "url": "https://europeremotely.com/"},
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

                    # Create/update Company
                    company_obj, created = Company.objects.get_or_create(
                        name=company_name,
                        defaults={
                            "logo": company_logo,
                            "platform": platform,
                        },
                    )

                    # Update logo if empty
                    if not company_obj.logo:
                        company_obj.logo = company_logo
                        company_obj.save()

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
                company_obj = Company.objects.get(name=company_name)
                qs = Job.objects.filter(platform=platform, company=company_obj)
                if found_ids:
                    qs.exclude(external_job_id__in=found_ids).update(is_active=False)
            except Company.DoesNotExist:
                logger.warning("Company '%s' not found in DB, skipping inactivation.", company_name)
            except Exception:
                logger.exception("Failed to mark inactive jobs for %s (%s)", company_name, platform)

        logger.info("Total jobs fetched/updated: %d", total)



# from django.core.management.base import BaseCommand
# from jobs.models import Company, Job
# from jobs.utils import parse_date
# import logging
# from jobs import fetchers
# import requests

# logger = logging.getLogger(__name__)

# LOGO_DEV_PUBLIC_KEY = 'pk_K96TtQYUTvy3hHXDyIEUqw'

# # Helper function to get company logo URL from logo.dev
# def get_company_logo(company_name: str) -> str:
#     """
#     Returns the logo.dev URL for a company name.
#     Checks if the URL is reachable, otherwise returns empty string.
#     """
#     safe_name = company_name.lower().replace(" ", "")
#     url = "https://img.logo.dev/name/{safe_name}?token={LOGO_DEV_PUBLIC_KEY}&size=101&retina=true"



#     try:
#         response = requests.get(url, timeout=5)
#         response.raise_for_status()
#         return url
#     except requests.RequestException:
#         return ""


# # Example companies
# COMPANIES = [
#     # Greenhouse companies
#     {"name": "Help Scout", "platform": "greenhouse", "handle": "helpscout"},
#     {"name": "Zapier", "platform": "greenhouse", "handle": "zapier"},
#     {"name": "Drift", "platform": "greenhouse", "handle": "drift"},
#     {"name": "Intercom", "platform": "greenhouse", "handle": "intercom"},
#     {"name": "Trello", "platform": "greenhouse", "handle": "trello"},
#     {"name": "Figma", "platform": "greenhouse", "handle": "figma"},
#     {"name": "Notion", "platform": "greenhouse", "handle": "notion"},
#     {"name": "Stripe", "platform": "greenhouse", "handle": "stripe"},
#     {"name": "Plaid", "platform": "greenhouse", "handle": "plaid"},
#     # Lever companies
#     {"name": "Chipper", "platform": "lever", "handle": "chipper"},
#     {"name": "Toggl", "platform": "lever", "handle": "toggl"},
#     {"name": "Gusto", "platform": "lever", "handle": "gusto"},
#     {"name": "Lattice", "platform": "lever", "handle": "lattice"},
#     {"name": "Notion", "platform": "lever", "handle": "notion"},
#     # Workable companies
#     {"name": "Typeform", "platform": "workable", "handle": "typeform"},
#     {"name": "FrontApp", "platform": "workable", "handle": "frontapp"},
#     {"name": "Figma", "platform": "workable", "handle": "figma"},
#     {"name": "Miro", "platform": "workable", "handle": "miro"},
#     {"name": "Doist", "platform": "workable", "handle": "doist"},
#     # Generic career pages
#     {"name": "Breneo", "platform": "career_page", "url": "https://breneo.app/careers"},
#     {"name": "Acme Corp", "platform": "career_page", "url": "https://example.com/careers"},
#     {"name": "RemoteOK", "platform": "career_page", "url": "https://remoteok.com/remote-jobs"},
#     {"name": "WeWorkRemotely", "platform": "career_page", "url": "https://weworkremotely.com/categories/remote-programming-jobs"},
#     {"name": "EuropeRemotely", "platform": "career_page", "url": "https://europeremotely.com/"},
# ]

# PLATFORM_TO_FETCHER = {
#     "greenhouse": fetchers.fetch_greenhouse,
#     "lever": fetchers.fetch_lever,
#     "workable": fetchers.fetch_workable,
#     "smartrecruiters": getattr(fetchers, "fetch_smartrecruiters", None),
#     "rss": fetchers.fetch_rss,
#     "jobs.ge": fetchers.fetch_jobs_ge_listings,
#     "career_page": fetchers.fetch_generic_career_page,
#     "ashby": fetchers.fetch_ashby,
# }


# class Command(BaseCommand):
#     help = "Fetch jobs from configured companies and store/update in DB"

#     def handle(self, *args, **options):
#         total = 0
#         for comp in COMPANIES:
#             platform = comp.get("platform")
#             company_name = comp.get("name")
#             company_logo = get_company_logo(company_name)

#             logger.info("Fetching jobs for %s (%s)", company_name, platform)

#             fetcher = PLATFORM_TO_FETCHER.get(platform)
#             if not fetcher:
#                 logger.warning("No fetcher for platform: %s", platform)
#                 continue

#             if platform in ("greenhouse", "lever", "workable", "smartrecruiters"):
#                 jobs_data = fetcher(comp.get("handle"), company_name)
#             else:
#                 jobs_data = fetcher(comp.get("url") or comp.get("handle"), company_name)

#             found_ids = set()
#             for j in jobs_data:
#                 try:
#                     ext_id = j.get("external_job_id") or j.get("apply_url")
#                     if not ext_id:
#                         continue
#                     found_ids.add(ext_id)

#                     # Create/update Company with logo
#                     company_name_final = j.get("company") or company_name
#                     company_obj, created = Company.objects.get_or_create(
#                         name=company_name_final,
#                         defaults={"logo": get_company_logo(company_name_final)}
#                     )

#                     # Update logo if empty
#                     if not company_obj.logo:
#                         company_obj.logo = get_company_logo(company_name_final)
#                         company_obj.save()

#                     # Create/update Job
#                     defaults = {
#                         "title": j.get("title") or "",
#                         "company": company_obj,
#                         "location": j.get("location"),
#                         "description": j.get("description"),
#                         "apply_url": j.get("apply_url") or ext_id,
#                         "posted_at": parse_date(j.get("posted_at")) if j.get("posted_at") else None,
#                         "raw": j.get("raw") or {},
#                         "is_active": True,
#                     }

#                     Job.objects.update_or_create(
#                         platform=platform,
#                         external_job_id=ext_id,
#                         defaults=defaults,
#                     )
#                     total += 1

#                 except Exception:
#                     logger.exception("Failed to save job: %s", j.get("title"))

#             # Mark old jobs inactive
#             try:
#                 company_obj = Company.objects.get(name=company_name)
#                 qs = Job.objects.filter(platform=platform, company=company_obj)
#                 if found_ids:
#                     qs.exclude(external_job_id__in=found_ids).update(is_active=False)
#             except Company.DoesNotExist:
#                 logger.warning("Company '%s' not found in DB, skipping inactivation.", company_name)
#             except Exception:
#                 logger.exception("Failed to mark inactive jobs for %s (%s)", company_name, platform)

#         logger.info("Total jobs fetched/updated: %d", total)
