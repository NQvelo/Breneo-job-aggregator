from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.conf import settings as django_settings
from jobs.models import Company, Job
from jobs.utils import parse_date, process_job_description
from jobs.job_posting_parser import parse_job_posting_for_db
from jobs.job_normalizer import normalize_job_fields
from jobs.matching_normalizer import extract_visa_sponsorship, extract_work_authorization_required
from jobs.industry_taxonomy import IndustryContext, determine_industry
from jobs import fetchers
import logging
import sys

logger = logging.getLogger(__name__)
# Configure logging to ensure errors are visible in cron jobs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)

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
    # LinkedIn: no public API. To use a third-party API, set LINKEDIN_JOBS_API_URL (and optional KEY) and add:
    # {"name": "LinkedIn Jobs", "platform": "linkedin", "url": "<your API URL>"}
]

def _compute_industry_tags(job_obj, raw_job_dict, created, logger_instance):
    """Set job_obj.industry_tags from title/description/company. Does not save."""
    should_compute = (
        created
        or not (job_obj.industry_tags or "")
        or job_obj.title != raw_job_dict.get("title")
        or job_obj.description != raw_job_dict.get("description")
    )
    if not should_compute:
        return
    try:
        source_industry = None
        if isinstance(job_obj.raw, dict):
            source_industry = (
                job_obj.raw.get("industry")
                or job_obj.raw.get("category")
                or job_obj.raw.get("sector")
            )
        if not source_industry and job_obj.company and getattr(job_obj.company, "additional_details", None):
            if isinstance(job_obj.company.additional_details, dict):
                source_industry = (
                    job_obj.company.additional_details.get("industry")
                    or job_obj.company.additional_details.get("sector")
                )
        ctx = IndustryContext(
            title=job_obj.title or "",
            description_raw=job_obj.description or "",
            company_name=job_obj.company.name if job_obj.company else "",
            source_industry_field=source_industry,
        )
        tags = determine_industry(ctx)
        job_obj.industry_tags = ", ".join(tags) if tags else ""
    except Exception as e:
        logger_instance.warning("Industry determination failed for %s: %s", job_obj.title, e)


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
    "linkedin": fetchers.fetch_linkedin,
}

class Command(BaseCommand):
    help = "Fetch jobs from configured companies and store/update in DB"

    def handle(self, *args, **options):
        try:
            # Verify database connection
            from django.db import connection
            connection.ensure_connection()
            
            self.stdout.write(self.style.SUCCESS("Starting job fetch..."))
            logger.info("Starting job fetch command")
            
        except Exception as e:
            error_msg = f"Database connection failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
            sys.exit(1)
        
        total = 0
        errors = []
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
                elif platform == "linkedin":
                    api_url = comp.get("url") or getattr(django_settings, "LINKEDIN_JOBS_API_URL", None)
                    api_key = comp.get("api_key") or getattr(django_settings, "LINKEDIN_JOBS_API_KEY", None)
                    jobs_data = fetcher(api_url, company_name, api_key=api_key) if api_url else []
                else:
                    jobs_data = fetcher(comp.get("url") or comp.get("handle"), company_name)
            except Exception as e:
                error_msg = f"Error fetching jobs for {company_name}: {str(e)}"
                logger.exception(error_msg)
                self.stdout.write(self.style.ERROR(f"  ✗ {error_msg}"))
                errors.append(error_msg)
                continue

            if not jobs_data:
                self.stdout.write(self.style.WARNING(f"  ⊘ No jobs found for {company_name}"))
                continue

            found_ids = set()
            company_job_count = 0
            # Process jobs in batches to avoid transaction issues
            batch_size = 50
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
                    
                    # Auto-fill parsed data for every new/updated job (responsibilities, qualifications, summary, workplace_type, skills_required)
                    if job_obj.description:
                        try:
                            parsed = parse_job_posting_for_db(job_obj.description, location=job_obj.location or "")
                            updated = False
                            if parsed.get("responsibilities"):
                                job_obj.responsibilities = parsed["responsibilities"]
                                updated = True
                            if parsed.get("qualifications"):
                                job_obj.qualifications = parsed["qualifications"]
                                updated = True
                            if parsed.get("job_description_summary"):
                                if not job_obj.structured_description:
                                    job_obj.structured_description = {}
                                if isinstance(job_obj.structured_description, dict):
                                    job_obj.structured_description["summary"] = parsed["job_description_summary"]
                                    updated = True
                            if parsed.get("workplace_type"):
                                job_obj.workplace_type = parsed["workplace_type"]
                                updated = True
                            if parsed.get("skills_required"):
                                job_obj.skills_required = parsed["skills_required"]
                                updated = True
                            if updated:
                                job_obj.save(update_fields=[
                                    "responsibilities", "qualifications", "structured_description",
                                    "workplace_type", "skills_required",
                                ])
                        except Exception as e:
                            logger.warning(f"Job posting parser failed for {job_obj.title}: {e}")
                        # Also run process_job_description for benefits, etc.
                        try:
                            processed = process_job_description(job_obj.description)
                            if processed:
                                updated = False
                                if processed.get("benefits"):
                                    job_obj.benefits = processed.get("benefits")
                                    updated = True
                                if not job_obj.structured_description:
                                    job_obj.structured_description = {}
                                if isinstance(job_obj.structured_description, dict):
                                    job_obj.structured_description.update({
                                        "company_overview": processed.get("company_overview"),
                                        "role_description": processed.get("role_description"),
                                    })
                                    updated = True
                                if updated:
                                    job_obj.save(update_fields=[
                                        "benefits", "structured_description"
                                    ])
                        except Exception as e:
                            logger.warning(f"Failed to process job description for {job_obj.title}: {e}")

                    # Always populate matching fields for this fetched job (work_mode, seniority, role_category, skills, etc.)
                    if job_obj.title and (job_obj.description or job_obj.qualifications):
                        try:
                            norm = normalize_job_fields(
                                title=job_obj.title,
                                description_raw=job_obj.description,
                                location=job_obj.location,
                                qualifications_text=job_obj.qualifications,
                            )
                            job_obj.work_mode = norm.get("work_mode", "unknown")
                            job_obj.seniority = norm.get("seniority", "unknown")
                            job_obj.role_category = norm.get("role_category")
                            job_obj.min_years_experience = norm.get("min_years_experience")
                            job_obj.skills_required = norm.get("skills_required") or []
                            job_obj.skills_preferred = norm.get("skills_preferred") or []
                            job_obj.tech_stack = norm.get("tech_stack") or []
                            job_obj.tech_stack_candidates = norm.get("tech_stack_candidates") or []
                            job_obj.languages_required = norm.get("languages_required") or []
                            job_obj.embedding_text = norm.get("embedding_text")
                            job_obj.data_completeness_score = norm.get("data_completeness_score", 0)
                            job_obj.location_country = norm.get("location_country")
                            job_obj.visa_sponsorship = extract_visa_sponsorship(job_obj.description) or "unknown"
                            job_obj.work_authorization_required = extract_work_authorization_required(job_obj.description) or "unknown"
                            _compute_industry_tags(job_obj, j, created, logger)
                            job_obj.save(update_fields=[
                                "work_mode", "seniority", "role_category", "min_years_experience",
                                "skills_required", "skills_preferred", "tech_stack", "tech_stack_candidates",
                                "languages_required", "embedding_text", "data_completeness_score",
                                "location_country", "visa_sponsorship", "work_authorization_required",
                                "industry_tags",
                            ])
                        except Exception as e:
                            logger.warning(f"Matching fields normalizer failed for {job_obj.title}: {e}")
                    else:
                        # No description/qualifications: still compute industry_tags from title + company
                        if job_obj.title:
                            _compute_industry_tags(job_obj, j, created, logger)
                            job_obj.save(update_fields=["industry_tags"])
                    
                    total += 1
                    company_job_count += 1
                    
                    # Commit in batches to ensure persistence without slowing down too much
                    if company_job_count % batch_size == 0:
                        transaction.commit()
                        logger.debug(f"Committed batch of {batch_size} jobs for {company_name}")

                except Exception as e:
                    error_msg = f"Failed to save job {j.get('title')}: {str(e)}"
                    logger.exception(error_msg)
                    errors.append(error_msg)

            # Mark old jobs inactive
            try:
                qs = Job.objects.filter(platform=platform, company=company_obj)
                if found_ids:
                    inactive_count = qs.exclude(external_job_id__in=found_ids).update(is_active=False)
                    if inactive_count > 0:
                        self.stdout.write(f"  ⊘ Marked {inactive_count} old jobs as inactive")
                        # Explicitly commit transaction
                        transaction.commit()
            except Exception as e:
                error_msg = f"Failed to mark inactive jobs for {company_name} ({platform}): {str(e)}"
                logger.exception(error_msg)
                errors.append(error_msg)

            self.stdout.write(self.style.SUCCESS(f"  ✓ Fetched {company_job_count} jobs for {company_name}"))

        # Final commit to ensure all changes are persisted
        transaction.commit()

        # Delete inactive jobs from the dataset (no longer in feeds)
        try:
            deleted_count, _ = Job.objects.filter(is_active=False).delete()
            if deleted_count > 0:
                transaction.commit()
                self.stdout.write(self.style.WARNING(f"  🗑 Deleted {deleted_count} inactive job(s) from the dataset"))
                logger.info("Deleted %d inactive jobs from the dataset", deleted_count)
        except Exception as e:
            logger.exception("Failed to delete inactive jobs: %s", e)
            self.stdout.write(self.style.WARNING(f"  ⚠ Could not delete inactive jobs: {e}"))
        
        # Verify jobs were actually saved to database
        try:
            connection.close()  # Close connection to force flush
            
            # Reconnect and verify
            connection.ensure_connection()
            
            # Count active jobs in database
            saved_count = Job.objects.filter(is_active=True).count()
            self.stdout.write(f"  📊 Active jobs in database: {saved_count}")
            logger.info("Active jobs in database after fetch: %d", saved_count)
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ Could not verify database: {str(e)}"))
            logger.warning("Could not verify database after fetch: %s", str(e))
        
        self.stdout.write('')
        if errors:
            self.stdout.write(self.style.WARNING(f"Encountered {len(errors)} errors during fetch"))
            for error in errors[:5]:  # Show first 5 errors
                logger.error(error)
        
        if total > 0:
            self.stdout.write(self.style.SUCCESS(f"✓ Successfully fetched/updated {total} jobs"))
            logger.info("Job fetch completed successfully. Total jobs: %d", total)
        else:
            self.stdout.write(self.style.WARNING("⚠ No new jobs were fetched"))
            logger.warning("Job fetch completed but no jobs were found/updated")
        
        # Django management commands should not return values from handle()
        # All output is already written to self.stdout above
        # Exit code is automatically 0 (success) unless an exception occurs


