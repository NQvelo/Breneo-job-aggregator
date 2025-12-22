from rest_framework import serializers
from .models import Job, Company
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


class NestedJobSerializer(serializers.ModelSerializer):
    """Serializer for jobs nested within company data"""
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_logo = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = [
            'id', 'title', 'company_name', 'company_logo', 'location', 'description', 'apply_url', 'platform',
            'external_job_id', 'posted_at', 'fetched_at', 'is_active', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at']
    
    def get_company_logo(self, obj):
        """Get company logo in the correct format"""
        from jobs.fetchers import get_logo_url
        
        # Use company logo if it exists and is in correct format
        if obj.company.logo and 'img.logo.dev/name/' in obj.company.logo:
            return obj.company.logo
        
        # Generate logo URL using the correct format
        return get_logo_url(obj.company.name)


class CompanyJobsSerializer(serializers.ModelSerializer):
    """Serializer for companies with nested jobs"""
    jobs = serializers.SerializerMethodField()
    domain = serializers.CharField(allow_blank=True, allow_null=True)
    logo = serializers.SerializerMethodField()
    
    class Meta:
        model = Company
        fields = ['id', 'name', 'domain', 'logo', 'platform', 'jobs']
    
    def get_logo(self, obj):
        """Ensure logo uses the correct format: https://img.logo.dev/name/{name}?token=..."""
        from jobs.fetchers import get_logo_url
        
        # If logo exists and is in the correct format, return it
        if obj.logo and 'img.logo.dev/name/' in obj.logo:
            return obj.logo
        
        # Otherwise, generate the logo URL using the correct format
        return get_logo_url(obj.name)
    
    def get_jobs(self, obj):
        # Filter only active jobs and serialize them
        active_jobs = obj.jobs.filter(is_active=True)
        return NestedJobSerializer(active_jobs, many=True).data
    
    def to_representation(self, instance):
        """Ensure domain is empty string instead of None"""
        representation = super().to_representation(instance)
        if representation.get('domain') is None:
            representation['domain'] = ''
        return representation


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