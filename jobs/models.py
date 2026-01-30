from django.db import models
import logging

logger = logging.getLogger(__name__)


class Company(models.Model):
    name = models.CharField(max_length=200, unique=True)

    # Optional domain (useful for enrichment / logo fetching)
    domain = models.CharField(max_length=200, blank=True, null=True)

    # Logo URL (Logo.dev, etc.)
    logo = models.URLField(blank=True, null=True, help_text="Company logo URL")

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class Job(models.Model):
    title = models.CharField(max_length=500)

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="jobs",
    )

    # Location fields
    location = models.CharField(max_length=200, blank=True, null=True)

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
    
    team_description = models.TextField(
        blank=True,
        null=True,
        help_text="Team description from job posting, if available"
    )
    
    benefits = models.TextField(
        blank=True,
        null=True,
        help_text="Benefits section from job posting, if available"
    )
    
    apply_url = models.URLField(blank=True, null=True)

    platform = models.CharField(
        max_length=100,
        help_text="Source platform (greenhouse, lever, ashby, workable, etc.)",
    )

    external_job_id = models.CharField(
        max_length=255,
        help_text="Job ID from external platform",
    )

    posted_at = models.DateTimeField(blank=True, null=True)
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
        
        # Parse job posting (robust parser) for responsibilities, qualifications, and summary
        if self.description and (not self.responsibilities or not self.qualifications):
            try:
                from .job_posting_parser import parse_job_posting_for_db
                parsed = parse_job_posting_for_db(self.description)
                if parsed.get("responsibilities") and not self.responsibilities:
                    self.responsibilities = parsed["responsibilities"]
                if parsed.get("qualifications") and not self.qualifications:
                    self.qualifications = parsed["qualifications"]
                if parsed.get("job_description_summary"):
                    if not self.structured_description:
                        self.structured_description = {}
                    if isinstance(self.structured_description, dict):
                        self.structured_description["summary"] = parsed["job_description_summary"]
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
        
        # Parse structured description if description exists and structured_description is empty
        if self.description and not self.structured_description:
            from .utils import parse_structured_description
            try:
                self.structured_description = parse_structured_description(self.description)
            except Exception:
                pass  # If parsing fails, continue without structured description
        
        # Process job description for team_description, benefits, and other structured fields
        if self.description:
            from .utils import process_job_description
            try:
                needs_processing = (
                    not self.team_description or
                    not self.benefits or
                    not self.structured_description
                )
                if needs_processing:
                    processed = process_job_description(self.description)
                    if processed:
                        if processed.get("team_description") and not self.team_description:
                            self.team_description = processed.get("team_description")
                        if processed.get("benefits") and not self.benefits:
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

