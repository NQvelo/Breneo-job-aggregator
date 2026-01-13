from django.core.management.base import BaseCommand
from jobs.models import Company, Job
from jobs.utils import parse_date, process_job_description
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
    {"name": "Stripe", "platform": "greenhouse", "handle": "stripe"},
    {"name": "Airbnb", "platform": "greenhouse", "handle": "airbnb"},
    {"name": "DoorDash", "platform": "greenhouse", "handle": "doordash"},
    {"name": "SpaceX", "platform": "greenhouse", "handle": "spacex"},
    {"name": "Cloudflare", "platform": "greenhouse", "handle": "cloudflare"},
    {"name": "Xometry", "platform": "greenhouse", "handle": "xometry"},
    {"name": "Reddit", "platform": "greenhouse", "handle": "reddit"},
    # Note: Apple removed - they use a custom ATS system with no public API or RSS feed
    # Note: Google and Meta removed due to ToS concerns - they don't provide official APIs
    # and scraping their career pages likely violates their Terms of Service
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
            # Update company if platform or logo changed
            updated_company = False
            if not company_obj.logo:
                company_obj.logo = company_logo
                updated_company = True
            if company_obj.platform != platform:
                company_obj.platform = platform
                updated_company = True
            if updated_company:
                company_obj.save()

            logger.info("Fetching jobs for %s (%s)", company_name, platform)
            self.stdout.write(f"Fetching jobs for {company_name} ({platform})...")

            fetcher = PLATFORM_TO_FETCHER.get(platform)
            if not fetcher:
                logger.warning("No fetcher for platform: %s", platform)
                self.stdout.write(self.style.ERROR(f"  ✗ No fetcher for platform: {platform}"))
                continue

            try:
                if platform in ("greenhouse", "lever", "workable", "smartrecruiters", "ashby"):
                    jobs_data = fetcher(comp.get("handle"), company_name)
                else:
                    jobs_data = fetcher(comp.get("url") or comp.get("handle"), company_name)
            except Exception as e:
                logger.exception("Error fetching jobs for %s", company_name)
                self.stdout.write(self.style.ERROR(f"  ✗ Error fetching: {str(e)}"))
                continue

            if not jobs_data:
                self.stdout.write(self.style.WARNING(f"  ⊘ No jobs found for {company_name}"))
                continue

            found_ids = set()
            company_job_count = 0
            for j in jobs_data:
                try:
                    ext_id = j.get("external_job_id") or j.get("apply_url")
                    if not ext_id:
                        continue
                    found_ids.add(ext_id)

                    # Create/update Job
                    job_obj, created = Job.objects.update_or_create(
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
                        },
                    )
                    
                    # Process job description to extract structured fields (responsibilities, qualifications, team_description, benefits)
                    # This ensures AI extraction happens during fetch, even if fields already exist
                    if job_obj.description:
                        try:
                            processed = process_job_description(job_obj.description)
                            if processed:
                                # Always update if we have processed data (to ensure latest extraction)
                                updated = False
                                
                                if processed.get('responsibilities'):
                                    job_obj.responsibilities = processed.get('responsibilities')
                                    updated = True
                                
                                if processed.get('qualifications'):
                                    job_obj.qualifications = processed.get('qualifications')
                                    updated = True
                                
                                if processed.get('team_description'):
                                    job_obj.team_description = processed.get('team_description')
                                    updated = True
                                
                                if processed.get('benefits'):
                                    job_obj.benefits = processed.get('benefits')
                                    updated = True
                                
                                # Update structured_description
                                if not job_obj.structured_description:
                                    job_obj.structured_description = {}
                                if isinstance(job_obj.structured_description, dict):
                                    job_obj.structured_description.update({
                                        'summary': processed.get('summary'),
                                        'company_overview': processed.get('company_overview'),
                                        'role_description': processed.get('role_description'),
                                    })
                                    updated = True
                                
                                # Save if we updated any fields
                                if updated:
                                    job_obj.save(update_fields=[
                                        'responsibilities', 'qualifications', 
                                        'team_description', 'benefits', 'structured_description'
                                    ])
                        except Exception as e:
                            logger.warning(f"Failed to process job description for {job_obj.title}: {e}")
                    
                    total += 1
                    company_job_count += 1

                except Exception:
                    logger.exception("Failed to save job: %s", j.get("title"))

            # Mark old jobs inactive
            try:
                qs = Job.objects.filter(platform=platform, company=company_obj)
                if found_ids:
                    inactive_count = qs.exclude(external_job_id__in=found_ids).update(is_active=False)
                    if inactive_count > 0:
                        self.stdout.write(f"  ⊘ Marked {inactive_count} old jobs as inactive")
            except Exception:
                logger.exception("Failed to mark inactive jobs for %s (%s)", company_name, platform)

            self.stdout.write(self.style.SUCCESS(f"  ✓ Fetched {company_job_count} jobs for {company_name}"))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f"Total jobs fetched/updated: {total}"))
        logger.info("Total jobs fetched/updated: %d", total)


