from django.db import models
import uuid


class Company(models.Model):
    name = models.CharField(max_length=200)
    platform = models.CharField(max_length=100, blank=True, null=True)
    handle = models.CharField(max_length=200, blank=True, null=True)
    logo = models.URLField(blank=True, null=True)
    careers_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Job(models.Model):
    # keep default AutoField primary key to match existing migrations/db
    title = models.CharField(max_length=500)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    apply_url = models.URLField(blank=True, null=True)
    # new fields to be added via migrations
    platform = models.CharField(max_length=100, blank=True, null=True)
    external_job_id = models.CharField(max_length=255, blank=True, null=True)
    posted_at = models.DateTimeField(blank=True, null=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    raw = models.JSONField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["platform", "external_job_id"], name="unique_platform_external_id")
        ]
        indexes = [
            models.Index(fields=["company"]),
            models.Index(fields=["posted_at"]),
            models.Index(fields=["platform", "external_job_id"]),
        ]

    def __str__(self):
        return f"{self.title} @ {self.company}"
