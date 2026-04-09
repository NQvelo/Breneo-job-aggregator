from django.db import models
import logging
from cloudinary_storage.storage import MediaCloudinaryStorage

logger = logging.getLogger(__name__)

# Matching field enums for job-user matching system
WORK_MODE_CHOICES = [
    ("remote", "Remote"),
    ("hybrid", "Hybrid"),
    ("onsite", "On-site"),
    ("unknown", "Unknown"),
]

SENIORITY_CHOICES = [
    ("intern", "Intern"),
    ("junior", "Junior"),
    ("mid", "Mid"),
    ("senior", "Senior"),
    ("lead", "Lead"),
    ("unknown", "Unknown"),
]

VISA_SPONSORSHIP_CHOICES = [
    ("yes", "Yes"),
    ("no", "No"),
    ("unknown", "Unknown"),
]

WORK_AUTH_CHOICES = [
    ("yes", "Yes"),
    ("no", "No"),
    ("unknown", "Unknown"),
]


class Industry(models.Model):
    """Canonical industry list for companies (managed in admin or via API)."""

    name = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Industries"

    def __str__(self) -> str:
        return self.name


class Company(models.Model):
    name = models.CharField(max_length=200, unique=True)

    industries = models.ManyToManyField(
        Industry,
        blank=True,
        related_name="companies",
        help_text="One or more industries (selectable)",
    )

    # Primary contact email (e.g. employer registration in breneo-api)
    company_email = models.EmailField(
        blank=True,
        null=True,
        help_text="Company contact email",
    )

    # Optional domain (useful for enrichment / logo fetching)
    domain = models.CharField(max_length=200, blank=True, null=True)

    # Logo URL (Logo.dev, external CDN, etc.) — optional when logo_upload is set
    logo = models.URLField(blank=True, null=True, help_text="Company logo URL")

    # Employer-uploaded logo (Cloudinary when CLOUDINARY_* env is set; else local media/)
    logo_upload = models.ImageField(
        upload_to="employer_logos/",
        blank=True,
        null=True,
        help_text="Uploaded company logo (multipart field name: logo_upload)",
    )
    employer_logo = models.ImageField(
        storage=MediaCloudinaryStorage(),
        upload_to="employer_logos/",
        blank=True,
        null=True,
        help_text="Uploaded employer profile logo (multipart field name: employer_logo)",
    )

    # Primary ATS platform (greenhouse, lever, ashby, etc.)
    platform = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Primary ATS platform (greenhouse, lever, ashby, etc.)",
    )

    # Company description (short and simple, 2 sentences)
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Short company description (2 sentences)",
        max_length=1000,
    )

    # Company website
    website = models.URLField(blank=True, null=True, help_text="Company website URL")

    # Founded date
    founded_date = models.DateField(blank=True, null=True, help_text="Company founding date")

    # Number of employees
    employees_count = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Number of employees (e.g., '1-10', '11-50', '51-200', '201-500', '501-1000', '1000+')",
    )

    # Social links (stored as JSON)
    social_links = models.JSONField(
        blank=True,
        null=True,
        help_text="Social media links (e.g., {'linkedin': '...', 'twitter': '...', 'github': '...'})",
        default=dict,
    )

    # Additional company details (stored as JSON for flexibility)
    additional_details = models.JSONField(
        blank=True,
        null=True,
        help_text="Additional company information (industry, headquarters, etc.)",
        default=dict,
    )

    # True when created via POST /api/employer/companies — not from job import; no auto-generated logo API
    employer_created = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class CompanyStaffMembership(models.Model):
    """Links a breneo-api user id (`external_user_id`) to a company for employer access."""

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="staff_memberships",
    )
    external_user_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="User id from breneo-api (string)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "external_user_id"],
                name="uniq_company_staff_external_user",
            )
        ]
        ordering = ["company_id", "id"]

    def __str__(self) -> str:
        return f"{self.company_id}:{self.external_user_id}"


class Job(models.Model):
    title = models.CharField(max_length=500)

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="jobs",
    )

    # Location fields
    location = models.CharField(max_length=200, blank=True, null=True)
    # Normalized country for matching/filtering (parsed from location)
    location_country = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Country parsed from location for job-user matching",
    )

    # Workplace type: Remote, Hybrid, On-site (extracted from job info)
    workplace_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Workplace type: Remote, Hybrid, or On-site",
    )

    # Skills required (array of skill strings, extracted from description)
    skills_required = models.JSONField(
        default=list,
        blank=True,
        help_text="List of required skills extracted from job posting",
    )

    # === MATCHING CORE FIELDS (for job-user matching system) ===
    # Normalized work mode enum for structured matching
    work_mode = models.CharField(
        max_length=20,
        choices=WORK_MODE_CHOICES,
        default="unknown",
        db_index=True,
        help_text="Work mode: remote, hybrid, onsite, or unknown",
    )
    # Seniority level for experience-based matching
    seniority = models.CharField(
        max_length=20,
        choices=SENIORITY_CHOICES,
        default="unknown",
        db_index=True,
        help_text="Seniority: intern, junior, mid, senior, lead, or unknown",
    )
    # Role category for domain matching (frontend, backend, data, etc.)
    role_category = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Role category inferred from title+skills: frontend, backend, data",
    )
    # Minimum years of experience when explicitly stated
    min_years_experience = models.IntegerField(
        blank=True,
        null=True,
        help_text="Minimum years of experience required (NULL if unknown)",
    )

    # === SKILLS ARRAYS (separate from skills_required for explicit required vs preferred) ===
    skills_preferred = models.JSONField(
        default=list,
        blank=True,
        help_text="Preferred/nice-to-have skills",
    )
    tech_stack = models.JSONField(
        default=list,
        blank=True,
        help_text="Technologies and tools used in the role",
    )
    # Unknown tech-like tokens for catalog expansion (not auto-added to skills)
    tech_stack_candidates = models.JSONField(
        default=list,
        blank=True,
        help_text="Tech-like tokens not in catalog, for review/expansion",
    )

    # Languages required (formatted as "English C1", "German B2", etc.)
    languages_required = models.JSONField(
        default=list,
        blank=True,
        help_text="Languages with CEFR level when mentioned (e.g. English C1)",
    )

    # === LEGAL / CONSTRAINTS ===
    visa_sponsorship = models.CharField(
        max_length=20,
        choices=VISA_SPONSORSHIP_CHOICES,
        default="unknown",
        help_text="Whether visa sponsorship is offered",
    )
    work_authorization_required = models.CharField(
        max_length=20,
        choices=WORK_AUTH_CHOICES,
        default="unknown",
        help_text="Whether work authorization is required",
    )

    # === AI / SEMANTIC MATCHING ===
    # Concatenated text for embedding generation
    embedding_text = models.TextField(
        blank=True,
        null=True,
        help_text="Text used for semantic embedding (title + skills + languages)",
    )
    # Vector stored as JSON list of floats (DB-agnostic; use pgvector for native vectors)
    embedding_vector = models.JSONField(
        blank=True,
        null=True,
        help_text="Semantic embedding vector as list of floats",
    )

    # === QUALITY / CONTROL ===
    data_completeness_score = models.IntegerField(
        default=0,
        help_text="Completeness score 0-100 for downranking low-quality jobs",
    )
    is_low_quality = models.BooleanField(default=False)
    is_duplicate = models.BooleanField(default=False)

    # Canonical industry tags for matching/filtering (comma-separated string)
    # Stored as: "banking, fintech, payments"
    industry_tags = models.TextField(
        blank=True,
        null=True,
        db_column="industryTags",
        help_text="Canonical industry tags, comma-separated, lowercase, deduplicated, sorted alphabetically",
    )

    description = models.TextField(blank=True, null=True)
    
    # Extracted sections from description using AI
    responsibilities = models.TextField(
        blank=True, 
        null=True, 
        help_text="Extracted responsibilities section from job description"
    )
    qualifications = models.TextField(
        blank=True, 
        null=True, 
        help_text="Extracted qualifications/requirements section from job description"
    )
    
    benefits = models.TextField(
        blank=True,
        null=True,
        help_text="Benefits section from job posting, if available"
    )
    
    apply_url = models.URLField(blank=True, null=True)

    # Compensation as free text (ranges, hourly, equity, etc.)
    salary = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Salary or compensation summary (as entered or normalized)",
    )

    platform = models.CharField(
        max_length=100,
        help_text="Source platform (greenhouse, lever, ashby, workable, etc.)",
    )

    external_job_id = models.CharField(
        max_length=255,
        help_text="Job ID from external platform",
    )

    posted_at = models.DateTimeField(blank=True, null=True, db_index=True)
    fetched_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    # Raw API payload for debugging / enrichment
    raw = models.JSONField(blank=True, null=True)
    
    # Structured description data (parsed from description field)
    structured_description = models.JSONField(blank=True, null=True, help_text="Parsed structured data from job description")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "external_job_id"],
                name="unique_platform_external_job",
            )
        ]
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"{self.title} @ {self.company.name}"

    def get_description_short(self, max_lines: int = 4, max_chars: int = 400) -> str:
        """Short summary for table/list display: ~4 lines max. Uses parsed summary if available."""
        if not self.description and not self.structured_description:
            return ""
        summary = None
        if self.structured_description and isinstance(self.structured_description, dict):
            summary = self.structured_description.get("summary") or ""
        if summary and summary.strip():
            lines = [ln.strip() for ln in summary.strip().split("\n") if ln.strip()][:max_lines]
            text = "\n".join(lines)
            return text[:max_chars] + ("..." if len(text) > max_chars else "")
        if not self.description:
            return ""
        lines = [ln.strip() for ln in self.description.strip().split("\n") if ln.strip()][:max_lines]
        text = "\n".join(lines)
        return text[:max_chars] + ("..." if len(text) > max_chars else "")

    def save(self, *args, **kwargs):
        # Clean description to ensure it's plain text (safety net)
        if self.description:
            from bs4 import BeautifulSoup
            import re
            try:
                # Check if description contains HTML tags
                if '<' in self.description and '>' in self.description:
                    soup = BeautifulSoup(self.description, "html.parser")
                    text = soup.get_text(separator="\n")
                    # Normalize whitespace
                    lines = [line.strip() for line in text.split("\n")]
                    text = "\n".join(line for line in lines if line)
                    text = re.sub(r'\n{3,}', '\n\n', text)
                    self.description = text.strip()
            except Exception:
                pass  # If cleaning fails, keep original description
        
        # Extract first_published from raw data if posted_at is not set
        if not self.posted_at and self.raw and isinstance(self.raw, dict):
            from .utils import parse_date
            first_published = self.raw.get("first_published")
            if first_published:
                parsed_date = parse_date(first_published)
                if parsed_date:
                    self.posted_at = parsed_date
        
        # Parse job posting (robust parser) for responsibilities, qualifications, summary, workplace_type, skills_required
        if self.description and (
            not self.responsibilities or not self.qualifications
            or not self.workplace_type or not self.skills_required
        ):
            try:
                from .job_posting_parser import parse_job_posting_for_db
                parsed = parse_job_posting_for_db(self.description, location=self.location or "")
                if parsed.get("responsibilities") and not self.responsibilities:
                    self.responsibilities = parsed["responsibilities"]
                if parsed.get("qualifications") and not self.qualifications:
                    self.qualifications = parsed["qualifications"]
                if parsed.get("job_description_summary"):
                    if not self.structured_description:
                        self.structured_description = {}
                    if isinstance(self.structured_description, dict):
                        self.structured_description["summary"] = parsed["job_description_summary"]
                if parsed.get("workplace_type") and not self.workplace_type:
                    self.workplace_type = parsed["workplace_type"]
                if parsed.get("skills_required") and not self.skills_required:
                    self.skills_required = parsed["skills_required"]
            except Exception as e:
                logger.warning(f"Job posting parser failed: {e}. Falling back to utils.")
                try:
                    from .utils import extract_responsibilities_and_qualifications
                    responsibilities, qualifications = extract_responsibilities_and_qualifications(
                        self.description
                    )
                    if responsibilities and not self.responsibilities:
                        self.responsibilities = responsibilities
                    if qualifications and not self.qualifications:
                        self.qualifications = qualifications
                except Exception as e2:
                    logger.warning(f"Fallback extraction failed: {e2}")
                # Still extract workplace_type and skills_required when main parser failed
                if not self.workplace_type or not self.skills_required:
                    try:
                        from .job_posting_parser import extract_workplace_type_and_skills
                        extracted = extract_workplace_type_and_skills(
                            self.description, self.location or ""
                        )
                        if extracted.get("workplace_type"):
                            self.workplace_type = extracted["workplace_type"]
                        if extracted.get("skills_required"):
                            self.skills_required = extracted["skills_required"]
                    except Exception as e3:
                        logger.warning(f"Workplace/skills extraction failed: {e3}")
        
        # Parse structured description if description exists and structured_description is empty
        if self.description and not self.structured_description:
            from .utils import parse_structured_description
            try:
                self.structured_description = parse_structured_description(self.description)
            except Exception:
                pass  # If parsing fails, continue without structured description
        
        # Process job description for benefits and other structured fields
        if self.description:
            from .utils import process_job_description, is_valid_benefits_text
            try:
                needs_processing = (
                    not self.benefits or
                    not self.structured_description
                )
                if needs_processing:
                    processed = process_job_description(self.description)
                    if processed:
                        if processed.get("benefits") and is_valid_benefits_text(processed.get("benefits")) and not self.benefits:
                            self.benefits = processed.get("benefits")
                        if not self.structured_description:
                            self.structured_description = {}
                        if isinstance(self.structured_description, dict):
                            self.structured_description.update({
                                "summary": processed.get("summary") or self.structured_description.get("summary"),
                                "company_overview": processed.get("company_overview"),
                                "role_description": processed.get("role_description"),
                            })
            except Exception as e:
                logger.warning(f"Failed to process job description: {e}")

        # Drop scraped ATS junk stored in benefits (pay range / ITAR placeholders)
        if self.benefits:
            from .utils import is_valid_benefits_text
            if not is_valid_benefits_text(self.benefits):
                self.benefits = ""

        # Normalize industry_tags formatting (lowercase, dedupe, sort, comma+space)
        if self.industry_tags:
            try:
                # Split on comma, trim whitespace, lowercase, drop empties
                raw_tags = [t.strip().lower() for t in self.industry_tags.split(",")]
                unique = sorted({t for t in raw_tags if t})
                self.industry_tags = ", ".join(unique) if unique else ""
            except Exception:
                # If normalization fails, keep original string to avoid data loss
                pass

        # Populate matching fields from title + description (catalog-based extraction)
        # Regenerate when title/description available and (new job OR derived fields empty)
        _should_normalize = self.title and (
            not self.pk
            or not self.skills_required
            or self.work_mode == "unknown"
            or not self.role_category
        )
        if _should_normalize and (self.description or self.qualifications):
            try:
                from .job_normalizer import normalize_job_fields
                norm = normalize_job_fields(
                    title=self.title,
                    description_raw=self.description,
                    location=self.location,
                    qualifications_text=self.qualifications,
                )
                self.work_mode = norm.get("work_mode", "unknown")
                self.seniority = norm.get("seniority", "unknown")
                self.role_category = norm.get("role_category")
                self.min_years_experience = norm.get("min_years_experience")
                self.skills_required = norm.get("skills_required") or []
                self.skills_preferred = norm.get("skills_preferred") or []
                self.tech_stack = norm.get("tech_stack") or []
                self.tech_stack_candidates = norm.get("tech_stack_candidates") or []
                self.languages_required = norm.get("languages_required") or []
                self.embedding_text = norm.get("embedding_text")
                self.data_completeness_score = norm.get("data_completeness_score", 0)
                self.location_country = norm.get("location_country")
                # Keep visa/auth from matching_normalizer if needed (job_normalizer doesn't extract these)
                from .matching_normalizer import extract_visa_sponsorship, extract_work_authorization_required
                self.visa_sponsorship = extract_visa_sponsorship(self.description) or "unknown"
                self.work_authorization_required = extract_work_authorization_required(self.description) or "unknown"
            except Exception as e:
                logger.warning(f"Job normalizer failed: {e}")

        # Employer-posted jobs: preserve submitted work mode / workplace label (NLP must not override)
        if self.raw and isinstance(self.raw, dict) and self.raw.get("source") == "employer":
            submitted = self.raw.get("employer_submitted") or {}
            wm = submitted.get("work_mode")
            valid_wm = {c[0] for c in WORK_MODE_CHOICES}
            if wm in valid_wm:
                self.work_mode = wm
            wt = submitted.get("workplace_type")
            if wt:
                self.workplace_type = wt
        
        super().save(*args, **kwargs)



# from django.db import models


# class Company(models.Model):
#     name = models.CharField(max_length=200, unique=True)

#     # Optional but very useful for logo + enrichment
#     domain = models.CharField(max_length=200, blank=True, null=True)

#     # Logo URL (Clearbit / Ashby / Greenhouse)
#     logo = models.URLField(blank=True, null=True)

#     platform = models.CharField(
#         max_length=100,
#         blank=True,
#         null=True,
#         help_text="Primary ATS platform (greenhouse, lever, ashby, etc.)",
#     )

#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ["name"]

#     def __str__(self):
#         return self.name


# class Job(models.Model):
#     title = models.CharField(max_length=500)

#     company = models.ForeignKey(
#         Company,
#         on_delete=models.CASCADE,
#         related_name="jobs",
#     )

#     # Location fields
#     location = models.CharField(max_length=200, blank=True, null=True)
#     location_country = models.CharField(max_length=100, blank=True, null=True)

#     description = models.TextField(blank=True, null=True)

#     apply_url = models.URLField(blank=True, null=True)

#     platform = models.CharField(
#         max_length=100,
#         help_text="Source platform (greenhouse, lever, ashby, workable, etc.)",
#     )

#     external_job_id = models.CharField(
#         max_length=255,
#         help_text="Job ID from external platform",
#     )

#     posted_at = models.DateTimeField(blank=True, null=True)

#     fetched_at = models.DateTimeField(auto_now=True)

#     is_active = models.BooleanField(default=True)

#     # Raw API payload for debugging / enrichment
#     raw = models.JSONField(blank=True, null=True)

#     # Company logo field
#     company_logo = models.URLField(blank=True, null=True)

#     class Meta:
#         constraints = [
#             models.UniqueConstraint(
#                 fields=["platform", "external_job_id"],
#                 name="unique_platform_external_job",
#             )
#         ]
#         ordering = ["-fetched_at"]

#     def __str__(self):
#         return f"{self.title} @ {self.company.name}"




# from django.db import models
# from django.utils import timezone


# class Job(models.Model):
#     title = models.CharField(max_length=500)
#     company = models.CharField(max_length=200)
#     location = models.CharField(max_length=200, blank=True, null=True)
#     description = models.TextField(blank=True, null=True)
#     apply_url = models.URLField(blank=True, null=True)

#     platform = models.CharField(max_length=100, blank=True, null=True)
#     external_job_id = models.CharField(max_length=255, blank=True, null=True)
#     posted_at = models.DateTimeField(blank=True, null=True)
#     fetched_at = models.DateTimeField(auto_now=True)
#     is_active = models.BooleanField(default=True)
#     raw = models.JSONField(blank=True, null=True)

#     class Meta:
#         constraints = [
#             models.UniqueConstraint(
#                 fields=["platform", "external_job_id"],
#                 name="unique_platform_external_id"
#             )
#         ]
#         indexes = [
#             models.Index(fields=["company"]),
#             models.Index(fields=["posted_at"]),
#             models.Index(fields=["platform", "external_job_id"]),
#         ]
#         ordering = ["-fetched_at"]

#     def __str__(self):
#         return f"{self.title} @ {self.company}"

#     def mark_inactive(self):
#         self.is_active = False
#         self.save(update_fields=["is_active", "fetched_at"])

