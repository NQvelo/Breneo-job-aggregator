
from rest_framework import serializers
from .models import Job, Company
from datetime import datetime

class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that takes an additional `fields` argument that
    controls which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields = kwargs.pop('fields', None)

        # Instantiate the superclass normally
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)


class JobSerializer(DynamicFieldsModelSerializer):
    company_logo = serializers.SerializerMethodField()
    description_short = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'company', 'company_logo', 'location', 'location_country',
            'workplace_type', 'work_mode', 'skills_required', 'skills_preferred', 'tech_stack', 'tech_stack_candidates',
            'seniority', 'role_category', 'min_years_experience', 'languages_required', 'industry_tags',
            'visa_sponsorship', 'work_authorization_required',
            'data_completeness_score', 'description', 'description_short', 'responsibilities', 'qualifications',
            'apply_url', 'platform', 'external_job_id', 'posted_at', 'fetched_at', 'is_active', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at']

    def get_description_short(self, obj):
        """Short description for table/list: max 4 lines."""
        return obj.get_description_short(max_lines=4, max_chars=400)

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


class CompanyInfoSerializer(DynamicFieldsModelSerializer):
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


class NestedJobSerializer(DynamicFieldsModelSerializer):
    """Serializer for jobs nested within company data"""
    company = CompanyInfoSerializer(read_only=True)
    description_short = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'company', 'location', 'location_country',
            'workplace_type', 'work_mode', 'skills_required', 'skills_preferred', 'tech_stack', 'tech_stack_candidates',
            'seniority', 'role_category', 'min_years_experience', 'languages_required', 'industry_tags',
            'visa_sponsorship', 'work_authorization_required', 'data_completeness_score',
            'description', 'description_short', 'responsibilities', 'qualifications',
            'apply_url', 'platform', 'external_job_id',
            'posted_at', 'fetched_at', 'is_active', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at']

    def get_description_short(self, obj):
        return obj.get_description_short(max_lines=4, max_chars=400)


class CompanyDetailSerializer(DynamicFieldsModelSerializer):
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
            "location_country": getattr(job, "location_country", None),
            "workplace_type": job.workplace_type,
            "work_mode": getattr(job, "work_mode", "unknown"),
            "skills_required": job.skills_required or [],
            "skills_preferred": getattr(job, "skills_preferred", []) or [],
            "tech_stack": getattr(job, "tech_stack", []) or [],
            "tech_stack_candidates": getattr(job, "tech_stack_candidates", []) or [],
            "seniority": getattr(job, "seniority", "unknown"),
            "role_category": getattr(job, "role_category", None),
            "min_years_experience": getattr(job, "min_years_experience", None),
            "languages_required": getattr(job, "languages_required", []) or [],
            "visa_sponsorship": getattr(job, "visa_sponsorship", "unknown"),
            "work_authorization_required": getattr(job, "work_authorization_required", "unknown"),
            "industry_tags": getattr(job, "industry_tags", "") or "",
            "data_completeness_score": getattr(job, "data_completeness_score", 0),
            "description": job.description,
            "description_short": job.get_description_short(max_lines=4, max_chars=400),
            "responsibilities": job.responsibilities,
            "qualifications": job.qualifications,
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
        desc = job.get("description") or ""
        lines = [ln.strip() for ln in desc.split("\n") if ln.strip()][:4]
        text = "\n".join(lines) if lines else ""
        description_short = text[:400] + ("..." if len(text) > 400 else "")
        return {
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "workplace_type": job.get("workplace_type"),
            "skills_required": job.get("skills_required") or [],
            "description": desc,
            "description_short": description_short,
            "responsibilities": job.get("responsibilities"),
            "qualifications": job.get("qualifications"),
            "apply_url": job.get("apply_url"),
            "platform": job.get("platform"),
            "external_job_id": job.get("external_job_id"),
            "posted_at": job.get("posted_at"),
            "is_active": job.get("is_active", True),
            "raw": job.get("raw"),
        }