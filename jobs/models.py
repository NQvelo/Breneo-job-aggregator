from django.db import models


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
        # Extract first_published from raw data if posted_at is not set
        if not self.posted_at and self.raw and isinstance(self.raw, dict):
            from .utils import parse_date
            first_published = self.raw.get("first_published")
            if first_published:
                parsed_date = parse_date(first_published)
                if parsed_date:
                    self.posted_at = parsed_date
        
        # Parse structured description if description exists and structured_description is empty
        if self.description and not self.structured_description:
            from .utils import parse_structured_description
            try:
                self.structured_description = parse_structured_description(self.description)
            except Exception:
                pass  # If parsing fails, continue without structured description
        
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

