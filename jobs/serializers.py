from rest_framework import serializers
from .models import Job, Company
from datetime import datetime


class JobSerializer(serializers.ModelSerializer):
    company_logo = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = [
            'id', 'title', 'company', 'company_logo', 'location',
            'description', 'apply_url', 'platform',
            'external_job_id', 'posted_at', 'fetched_at', 'is_active', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at']
    
    def get_company_logo(self, obj):
        """Get company logo from company model"""
        from jobs.fetchers import get_logo_url
        
        # Use company logo if it exists
        if obj.company and obj.company.logo:
            return obj.company.logo
        
        # Generate logo URL using the correct format
        if obj.company:
            return get_logo_url(obj.company.name)
        return None


class CompanyInfoSerializer(serializers.ModelSerializer):
    """Serializer for company information nested within job responses"""
    logo = serializers.SerializerMethodField()
    
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'domain', 'logo', 'platform', 'description', 'website',
            'founded_date', 'employees_count', 'social_links', 'additional_details',
        ]
        read_only_fields = ['id']
    
    def get_logo(self, obj):
        """Ensure logo uses the correct format: https://img.logo.dev/name/{name}?token=..."""
        from jobs.fetchers import get_logo_url
        
        # If logo exists and is in the correct format, return it
        if obj.logo and 'img.logo.dev/name/' in obj.logo:
            return obj.logo
        
        # Otherwise, generate the logo URL using the correct format
        return get_logo_url(obj.name)
    
    def to_representation(self, instance):
        """Ensure None values are handled properly"""
        representation = super().to_representation(instance)
        # Convert None to empty string for domain and website
        if representation.get('domain') is None:
            representation['domain'] = ''
        if representation.get('website') is None:
            representation['website'] = ''
        if representation.get('description') is None:
            representation['description'] = ''
        # Ensure social_links and additional_details are dicts, not None
        if representation.get('social_links') is None:
            representation['social_links'] = {}
        if representation.get('additional_details') is None:
            representation['additional_details'] = {}
        return representation


class NestedJobSerializer(serializers.ModelSerializer):
    """Serializer for jobs nested within company data"""
    company = CompanyInfoSerializer(read_only=True)
    
    class Meta:
        model = Job
        fields = [
            'id', 'title', 'company', 'location', 'description', 'apply_url', 'platform',
            'external_job_id', 'posted_at', 'fetched_at', 'is_active', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at']


class CompanyDetailSerializer(serializers.ModelSerializer):
    """Serializer for company details with all fields"""
    logo = serializers.SerializerMethodField()
    job_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'domain', 'logo', 'platform', 'description', 'website',
            'founded_date', 'employees_count', 'social_links', 'additional_details',
            'created_at', 'updated_at', 'job_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_logo(self, obj):
        """Ensure logo uses the correct format: https://img.logo.dev/name/{name}?token=..."""
        from jobs.fetchers import get_logo_url
        
        # If logo exists and is in the correct format, return it
        if obj.logo and 'img.logo.dev/name/' in obj.logo:
            return obj.logo
        
        # Otherwise, generate the logo URL using the correct format
        return get_logo_url(obj.name)
    
    def get_job_count(self, obj):
        """Get count of active jobs for this company"""
        return obj.jobs.filter(is_active=True).count()
    
    def to_representation(self, instance):
        """Ensure None values are handled properly"""
        representation = super().to_representation(instance)
        # Convert None to empty string for domain and website
        if representation.get('domain') is None:
            representation['domain'] = ''
        if representation.get('website') is None:
            representation['website'] = ''
        if representation.get('description') is None:
            representation['description'] = ''
        # Ensure social_links and additional_details are dicts, not None
        if representation.get('social_links') is None:
            representation['social_links'] = {}
        if representation.get('additional_details') is None:
            representation['additional_details'] = {}
        return representation


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