from rest_framework import serializers
from .models import Job
from datetime import datetime


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            'id', 'title', 'company',  "company_logo",  'location',
            'description', 'apply_url', 'platform',
            'external_job_id', 'posted_at', 'fetched_at', 'is_active', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at']


def job_to_dict(job):
    # job may be Job model instance or dict (from fetcher)
    if hasattr(job, "title"):
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description,
            "apply_url": job.apply_url,
            "platform": job.platform,
            "external_job_id": job.external_job_id,
            "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            "fetched_at": job.fetched_at.isoformat() if hasattr(job, "fetched_at") and job.fetched_at else None,
            "is_active": job.is_active,
            "raw": job.raw,
        }
    else:
        # assume dict from fetcher
        return {
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "description": job.get("description"),
            "apply_url": job.get("apply_url"),
            "platform": job.get("platform"),
            "external_job_id": job.get("external_job_id"),
            "posted_at": job.get("posted_at"),
            "is_active": job.get("is_active", True),
            "raw": job.get("raw"),
        }
