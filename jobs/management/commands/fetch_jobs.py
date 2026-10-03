from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from django.conf import settings as django_settings
from jobs.models import Company, Job
from jobs.utils import parse_date, process_job_description, is_valid_benefits_text
from jobs.job_posting_parser import parse_job_posting_for_db
from jobs.job_normalizer import normalize_job_fields, parse_stored_location_fields
from jobs.matching_normalizer import extract_visa_sponsorship, extract_work_authorization_required
from jobs.industry_taxonomy import determine_industry_tags
from jobs import fetchers
from jobs.remote_worldwide_filter import is_remote_worldwide_listing
import logging
import re
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


# Non–jobs.ge feeds: keep tech roles only (skip pure sales / ops / legal, etc.).
_TECH_ROLE_TITLE = re.compile(
    r"(?i)\b("
    r"engineer|engineering|developer|software|programmer|devops|sre|"
    r"backend|front[\s\-]?end|full[\s\-]?stack|fullstack|"
    r"data\s+(?:engineer|scientist|analyst)|machine\s+learning|ml\s+engineer|ai\s+engineer|"
    r"qa|quality\s+assurance|test\s+engineer|automation|"
    r"security\s+engineer|appsec|infosec|cyber|"
    r"platform|cloud|infrastructure|sysadmin|system\s+admin|"
    r"mobile|ios|android|react\s+native|flutter|"
    r"designer|ui/?ux|product\s+designer|product\s+manager|technical\s+program|"
    r"architect|cto|tech\s+lead|engineering\s+manager|"
    r"analyst|scientist|research\s+engineer"
    r")\b"
)
_NON_TECH_TITLE = re.compile(
    r"(?i)\b("
    r"account\s+executive|sales\s+(?:manager|director|rep|associate)|"
    r"recruiter|talent\s+acquisition|customer\s+success|"
    r"account\s+manager|marketing\s+manager|brand\s+manager|"
    r"legal\s+counsel|attorney|paralegal|receptionist|"
    r"office\s+manager|executive\s+assistant(?!\s+to\s+cto)|"
    r"copywriter|content\s+writer|social\s+media\s+manager"
    r")\b"
)


def _is_tech_role_listing(job_dict: dict) -> bool:
    """Heuristic title filter for ATS boards (not used for jobs.ge IT category)."""
    title = (job_dict.get("title") or "").strip()
    if not title:
        return False
    if _NON_TECH_TITLE.search(title):
        return False
    if _TECH_ROLE_TITLE.search(title):
        return True
    # Remotive / boards sometimes use stack names in the title
    desc_head = (job_dict.get("description") or "")[:800].lower()
    if any(
        tok in title.lower() or tok in desc_head
        for tok in (
            "python", "javascript", "typescript", "golang", "rust", "java",
            "kubernetes", "react", "node.js", "aws", "gcp", "azure",
        )
    ):
        return True
    return False


# Example companies — ATS boards. Non–jobs.ge saves require true worldwide remote + tech roles.
COMPANIES = [
    # jobs.ge IT/Programming: local GE tech (no worldwide filter)
    {
        "name": "Jobs.ge IT",
        "platform": "jobs.ge",
        "url": "https://jobs.ge/?cid=6",
        "dynamic_company": True,
    },
    # Greenhouse Job Board API
    {"name": "Intercom", "platform": "greenhouse", "handle": "intercom"},
    {"name": "Figma", "platform": "greenhouse", "handle": "figma"},
    {"name": "Stripe", "platform": "greenhouse", "handle": "stripe"},
    {"name": "Cloudflare", "platform": "greenhouse", "handle": "cloudflare"},
    {"name": "Reddit", "platform": "greenhouse", "handle": "reddit"},
    {"name": "Xometry", "platform": "greenhouse", "handle": "xometry"},
    # Lever Postings API
    {"name": "Spotify", "platform": "lever", "handle": "spotify"},
    # Ashby public job board GraphQL
    {"name": "Notion", "platform": "ashby", "handle": "notion"},
    {"name": "Ramp", "platform": "ashby", "handle": "ramp"},
    {"name": "Linear", "platform": "ashby", "handle": "linear"},
    # Remotive: remote board (still filtered to worldwide + tech)
    {
        "name": "Remotive",
        "platform": "remotive",
        "url": "https://remotive.com/api/remote-jobs",
        "dynamic_company": True,
    },
]

def _compute_industry_tags(job_obj, raw_job_dict, created, logger_instance):
    """Set job_obj.industry_tags from company + title (+ source). Does not save. If derived empty and existing set, keep existing."""
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
        tags_str, _source = determine_industry_tags(
            company_name=job_obj.company.name if job_obj.company else "",
            job_title=job_obj.title or "",
            source_industry=source_industry,
        )
        # If derived non-empty: overwrite. If derived empty and existing set: keep existing.
        if tags_str:
            job_obj.industry_tags = tags_str
        elif not (job_obj.industry_tags or "").strip():
            job_obj.industry_tags = ""
    except Exception as e:
        logger_instance.warning("Industry determination failed for %s: %s", job_obj.title, e)


# Map platform to fetcher function
PLATFORM_TO_FETCHER = {
    "greenhouse": fetchers.fetch_greenhouse,
    "lever": fetchers.fetch_lever,
    "workable": fetchers.fetch_workable,
    "smartrecruiters": fetchers.fetch_smartrecruiters,
    "remotive": fetchers.fetch_remotive,
    "adzuna": fetchers.fetch_adzuna,
    "rss": fetchers.fetch_rss,
    "jobs.ge": fetchers.fetch_jobs_ge_listings,
    "career_page": fetchers.fetch_generic_career_page,
    "ashby": fetchers.fetch_ashby,
    "linkedin": fetchers.fetch_linkedin,
}

# Fetched jobs missing from their feed for this long are deleted. Employer jobs are never touched.
STALE_JOB_GRACE_DAYS = 7

class Command(BaseCommand):
    help = "Fetch jobs from configured companies and store/update in DB"

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-jobs",
            type=int,
            default=None,
            metavar="N",
            help="Stop after saving/updating N jobs (useful for capped imports). Default: no limit.",
        )
        parser.add_argument(
            "--purge-jobs",
            action="store_true",
            help="Delete all jobs before fetching (companies are kept).",
        )
        parser.add_argument(
            "--remote-worldwide-only",
            action="store_true",
            help=(
                "Deprecated/no-op for most platforms: non–jobs.ge sources always require "
                "remote + worldwide. jobs.ge (local GE tech) is never filtered this way."
            ),
        )

    def handle(self, *args, **options):
        max_jobs = options.get("max_jobs")
        purge_jobs = options.get("purge_jobs")
        remote_worldwide_only = options.get("remote_worldwide_only")
        try:
            # Verify database connection
            from django.db import connection
            connection.ensure_connection()
            
            self.stdout.write(self.style.SUCCESS("Starting job fetch..."))
            if max_jobs is not None:
                self.stdout.write(f"  (max {max_jobs} job(s))")
            if purge_jobs:
                deleted, _ = Job.objects.all().delete()
                self.stdout.write(
                    self.style.WARNING(f"  Purged all jobs ({deleted} row(s) removed including related objects).")
                )
                logger.info("Purged all jobs before fetch (%s rows)", deleted)
            self.stdout.write(
                "  Filter: non–jobs.ge → remote+worldwide + tech roles; "
                "jobs.ge → all IT/Programming with sufficient detail"
            )
            if remote_worldwide_only:
                self.stdout.write("  (--remote-worldwide-only noted; already enforced for non–jobs.ge)")
            logger.info("Starting job fetch command")
            
        except Exception as e:
            error_msg = f"Database connection failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
            sys.exit(1)
        
        run_started_at = timezone.now()
        total = 0
        errors = []
        stop_fetching = False

        for comp in COMPANIES:
            if stop_fetching:
                break
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
                if platform == "smartrecruiters":
                    jobs_data = fetcher(
                        comp.get("handle"),
                        company_name,
                        logo=company_logo,
                        remote_only=comp.get("remote_only", True),
                    )
                elif platform == "remotive":
                    jobs_data = fetcher(
                        comp.get("url"),
                        company_name,
                        company_logo,
                    )
                elif platform == "adzuna":
                    jobs_data = fetcher(
                        company_name,
                        comp.get("handle") or "remote",
                        company_logo,
                    )
                elif platform in ("greenhouse", "lever", "workable", "ashby"):
                    jobs_data = fetcher(comp.get("handle"), company_name)
                elif platform == "linkedin":
                    api_url = comp.get("url") or getattr(django_settings, "LINKEDIN_JOBS_API_URL", None)
                    api_key = comp.get("api_key") or getattr(django_settings, "LINKEDIN_JOBS_API_KEY", None)
                    jobs_data = fetcher(api_url, company_name, api_key=api_key) if api_url else []
                elif platform == "jobs.ge":
                    jobs_data = fetcher(
                        comp.get("url") or "https://jobs.ge/?cid=6",
                        company_name,
                        logo=company_logo,
                        limit=comp.get("limit"),
                    )
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
            company_complete = True
            n_feed = len(jobs_data)
            batch_size = 50
            for idx, j in enumerate(jobs_data):
                try:
                    ext_id = j.get("external_job_id") or j.get("apply_url")
                    if ext_id is not None:
                        ext_id = str(ext_id).strip()[:255]
                    if not ext_id:
                        continue

                    # jobs.ge: keep local GE tech listings (no worldwide filter).
                    # All other platforms: remote+worldwide AND tech-role titles only.
                    if platform != "jobs.ge":
                        if not is_remote_worldwide_listing(j):
                            continue
                        if not _is_tech_role_listing(j):
                            continue

                    # Parse posted_at only when fetcher provided it; avoid overwriting with None
                    raw_posted = j.get("posted_at")
                    parsed_posted = parse_date(raw_posted) if raw_posted else None
                    raw_location = j.get("location")
                    ploc, pcountry = parse_stored_location_fields(raw_location)
                    # Fetcher may supply an explicit country (jobs.ge → Georgia)
                    explicit_country = (j.get("location_country") or "").strip() or None
                    if explicit_country:
                        pcountry = explicit_country
                    # jobs.ge already returns a clean city name (or None)
                    if platform == "jobs.ge":
                        ploc = (raw_location or "").strip() or None
                        pcountry = pcountry or "Georgia"

                    job_company_obj = company_obj
                    if comp.get("dynamic_company"):
                        co_name = ((j.get("company") or company_name) or "").strip() or company_name
                        if len(co_name) > 200:
                            co_name = co_name[:200]
                        job_company_obj, _ = Company.objects.get_or_create(
                            name=co_name,
                            defaults={
                                "logo": get_logo_url(co_name),
                                "platform": platform,
                            },
                        )

                    raw_apply = (j.get("apply_url") or "").strip()
                    # For most platforms the listing URL doubles as apply_url; for jobs.ge
                    # we only store a real registration link (or leave empty when email-only).
                    if not raw_apply and platform != "jobs.ge":
                        raw_apply = (ext_id or "").strip()
                    if len(raw_apply) > 2048:
                        raw_apply = raw_apply[:2048]

                    raw_apply_email = (j.get("apply_email") or "").strip() or None
                    if raw_apply_email and len(raw_apply_email) > 254:
                        raw_apply_email = raw_apply_email[:254]

                    defaults = {
                        "title": j.get("title") or "",
                        "company": job_company_obj,
                        "location": ploc if ploc is not None else raw_location,
                        "description": j.get("description"),
                        "apply_url": raw_apply or None,
                        "apply_email": raw_apply_email,
                        "raw": j.get("raw") or {},
                        "is_active": True,
                        "last_seen_at": run_started_at,
                    }
                    if pcountry is not None:
                        defaults["location_country"] = pcountry
                    if parsed_posted is not None:
                        defaults["posted_at"] = parsed_posted

                        # Check if job is older than 5 months (approx 150 days)
                        cutoff_date = timezone.now() - timedelta(days=150)
                        
                        # parsed_posted might be offset-naive or offset-aware
                        # Ensure we compare correctly
                        if timezone.is_aware(parsed_posted):
                            check_date = parsed_posted
                        else:
                            check_date = timezone.make_aware(parsed_posted, timezone.get_current_timezone())
                            
                        if check_date < cutoff_date:
                            self.stdout.write(f"  ⊘ Skipping job '{defaults['title']}' - posted too long ago ({parsed_posted})")
                            continue

                    job_obj, created = Job.objects.update_or_create(
                        platform=platform,
                        external_job_id=ext_id,
                        defaults=defaults,
                    )

                    # If posted_at still missing, try raw (first_published, updated_at, created_at)
                    if not job_obj.posted_at and isinstance(job_obj.raw, dict):
                        for key in ("first_published", "updated_at", "created_at", "postDate", "datePosted"):
                            val = job_obj.raw.get(key)
                            if val:
                                filled = parse_date(val)
                                if filled:
                                    job_obj.posted_at = filled
                                    job_obj.save(update_fields=["posted_at"])
                                    break

                    # Auto-fill parsed data for every new/updated job (responsibilities, qualifications, summary, workplace_type, skills_required)
                    if job_obj.description:
                        try:
                            parsed = parse_job_posting_for_db(
                                job_obj.description, location=(raw_location or job_obj.location or "")
                            )
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
                                b = processed.get("benefits")
                                if b and is_valid_benefits_text(b):
                                    job_obj.benefits = b
                                    updated = True
                                elif job_obj.benefits and not is_valid_benefits_text(job_obj.benefits):
                                    job_obj.benefits = ""
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
                    norm_applied = False
                    if job_obj.title and (job_obj.description or job_obj.qualifications):
                        try:
                            norm = normalize_job_fields(
                                title=job_obj.title,
                                description_raw=job_obj.description,
                                location=raw_location or job_obj.location,
                                qualifications_text=job_obj.qualifications,
                            )
                            norm_applied = True
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
                            if norm.get("canonical_location") is not None:
                                job_obj.location = norm["canonical_location"]
                            if norm.get("location_country") is not None:
                                job_obj.location_country = norm["location_country"]
                            job_obj.visa_sponsorship = extract_visa_sponsorship(job_obj.description) or "unknown"
                            job_obj.work_authorization_required = extract_work_authorization_required(job_obj.description) or "unknown"
                            _compute_industry_tags(job_obj, j, created, logger)
                            match_fields = [
                                "work_mode", "seniority", "role_category", "min_years_experience",
                                "skills_required", "skills_preferred", "tech_stack", "tech_stack_candidates",
                                "languages_required", "embedding_text", "data_completeness_score",
                                "visa_sponsorship", "work_authorization_required",
                                "industry_tags",
                            ]
                            if norm.get("canonical_location") is not None:
                                match_fields.append("location")
                            if norm.get("location_country") is not None:
                                match_fields.append("location_country")
                            job_obj.save(update_fields=match_fields)
                        except Exception as e:
                            logger.warning(f"Matching fields normalizer failed for {job_obj.title}: {e}")
                    else:
                        # No description/qualifications: still compute industry_tags from title + company
                        if job_obj.title:
                            _compute_industry_tags(job_obj, j, created, logger)
                            job_obj.save(update_fields=["industry_tags"])

                    if (
                        platform != "jobs.ge"
                        and norm_applied
                        and job_obj.work_mode in ("hybrid", "onsite")
                    ):
                        job_obj.delete()
                        continue

                    # Final guard: remote + country-specific must never stay in the table.
                    if platform != "jobs.ge":
                        check = {
                            "title": job_obj.title or "",
                            "location": job_obj.location or j.get("location") or "",
                            "location_country": job_obj.location_country or "",
                            "description": job_obj.description or j.get("description") or "",
                            "workplace_type": job_obj.workplace_type or j.get("workplace_type"),
                            "raw": job_obj.raw if isinstance(job_obj.raw, dict) else (j.get("raw") or {}),
                            "applicant_location_requirements": j.get("applicant_location_requirements"),
                        }
                        if not is_remote_worldwide_listing(check):
                            job_obj.delete()
                            continue

                    found_ids.add(ext_id)
                    total += 1
                    company_job_count += 1

                    if max_jobs is not None and total >= max_jobs:
                        if idx + 1 < n_feed:
                            company_complete = False
                        stop_fetching = True
                        break
                    
                    # Commit in batches to ensure persistence without slowing down too much
                    if company_job_count % batch_size == 0:
                        logger.debug(f"Processed batch of {batch_size} jobs for {company_name}")

                except Exception as e:
                    error_msg = f"Failed to save job {j.get('title')}: {str(e)}"
                    logger.exception(error_msg)
                    errors.append(error_msg)

            # Hide jobs no longer in this feed (only if we processed the full feed for this company;
            # skip when --max-jobs stopped mid-company to avoid wrong inactive flags).
            # The feed was non-empty, so an empty found_ids means nothing passed the filters.
            try:
                if company_complete:
                    if comp.get("dynamic_company"):
                        qs = Job.objects.filter(platform=platform)
                    else:
                        qs = Job.objects.filter(platform=platform, company=company_obj)
                    inactive_count = (
                        qs.filter(is_active=True)
                        .exclude(external_job_id__in=found_ids)
                        .update(is_active=False)
                    )
                    if inactive_count > 0:
                        self.stdout.write(f"  ⊘ Marked {inactive_count} old jobs as inactive")
            except Exception as e:
                error_msg = f"Failed to mark inactive jobs for {company_name} ({platform}): {str(e)}"
                logger.exception(error_msg)
                errors.append(error_msg)

            self.stdout.write(self.style.SUCCESS(f"  ✓ Fetched {company_job_count} jobs for {company_name}"))

        # Delete fetched jobs that have been missing from their feed for the whole grace period.
        # Covers removed companies and sources that keep failing; employer jobs are excluded.
        try:
            stale_cutoff = run_started_at - timedelta(days=STALE_JOB_GRACE_DAYS)
            stale_qs = Job.objects.filter(platform__in=PLATFORM_TO_FETCHER.keys()).filter(
                Q(last_seen_at__lt=stale_cutoff)
                | Q(last_seen_at__isnull=True, fetched_at__lt=stale_cutoff)
            )
            deleted_count, _ = stale_qs.delete()
            if deleted_count > 0:
                self.stdout.write(self.style.WARNING(
                    f"  🗑 Deleted {deleted_count} row(s) for jobs unseen for {STALE_JOB_GRACE_DAYS}+ days"
                ))
                logger.info("Deleted %d rows for jobs unseen for %d+ days", deleted_count, STALE_JOB_GRACE_DAYS)
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
            logger.warning("Job fetch completed but no jobs were found/updated")
            raise CommandError("No jobs were fetched from any source")


