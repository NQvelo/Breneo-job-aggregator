
from rest_framework import serializers
from .models import (
    Job,
    Company,
    CompanyStaffMembership,
    Industry,
    SENIORITY_CHOICES,
    VISA_SPONSORSHIP_CHOICES,
    WORK_AUTH_CHOICES,
)
from datetime import datetime


def company_staff_user_ids_for_api(company: Company) -> list[str]:
    """Breneo user ids for this company (from CompanyStaffMembership)."""
    cache = getattr(company, "_prefetched_objects_cache", None)
    if cache and "staff_memberships" in cache:
        return sorted({m.external_user_id for m in company.staff_memberships.all()})
    return list(
        company.staff_memberships.order_by("id").values_list("external_user_id", flat=True)
    )


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
            'salary', 'apply_url', 'platform', 'external_job_id', 'posted_at', 'fetched_at', 'is_active', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at']

    def get_description_short(self, obj):
        """Short description for table/list: max 4 lines."""
        return obj.get_description_short(max_lines=4, max_chars=400)

    def get_company_logo(self, obj):
        """Get company logo from company model"""
        from jobs.logo_url import resolved_company_logo_url

        if obj.company:
            return resolved_company_logo_url(obj.company, self.context.get("request"))
        return None


class IndustrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Industry
        fields = ["id", "name"]


class CompanyStaffMembershipSerializer(serializers.ModelSerializer):
    """Employer API: CRUD for company ↔ breneo user links."""

    company_id = serializers.PrimaryKeyRelatedField(
        source="company",
        queryset=Company.objects.all(),
    )

    class Meta:
        model = CompanyStaffMembership
        fields = ["id", "company_id", "external_user_id", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_external_user_id(self, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("This field may not be blank.")
        return v

    def validate(self, attrs):
        company = attrs.get("company", getattr(self.instance, "company", None))
        ext = attrs.get("external_user_id", getattr(self.instance, "external_user_id", None))
        if company is not None and ext is not None:
            qs = CompanyStaffMembership.objects.filter(company=company, external_user_id=ext)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"non_field_errors": ["This company already has this external_user_id."]}
                )
        return attrs


class CompanyInfoSerializer(DynamicFieldsModelSerializer):
    """Serializer for company information nested within job responses"""
    logo = serializers.SerializerMethodField()
    employer_logo = serializers.SerializerMethodField()
    industries = IndustrySerializer(many=True, read_only=True)
    staff_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'domain', 'logo', 'employer_logo', 'platform', 'description', 'website',
            'founded_date', 'employees_count', 'social_links', 'additional_details',
            'industries', 'company_email', 'staff_user_ids', 'employer_created',
        ]
        read_only_fields = ['id', 'employer_created']

    def get_staff_user_ids(self, obj):
        return company_staff_user_ids_for_api(obj)
    
    def get_logo(self, obj):
        from jobs.logo_url import resolved_company_logo_url

        return resolved_company_logo_url(obj, self.context.get("request"))

    def get_employer_logo(self, obj):
        if not getattr(obj, "employer_logo", None):
            return None
        url = obj.employer_logo.url
        if self.context.get("request") is not None and url.startswith("/"):
            return self.context["request"].build_absolute_uri(url)
        return url
    
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
            'salary', 'apply_url', 'platform', 'external_job_id',
            'posted_at', 'fetched_at', 'is_active', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at']

    def get_description_short(self, obj):
        return obj.get_description_short(max_lines=4, max_chars=400)


class CompanyDetailSerializer(DynamicFieldsModelSerializer):
    """Serializer for company details with all fields"""
    logo = serializers.SerializerMethodField()
    employer_logo = serializers.SerializerMethodField()
    job_count = serializers.SerializerMethodField()
    industries = IndustrySerializer(many=True, read_only=True)
    staff_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'domain', 'logo', 'employer_logo', 'platform', 'description', 'website',
            'founded_date', 'employees_count', 'social_links', 'additional_details',
            'industries', 'company_email', 'staff_user_ids',
            'created_at', 'updated_at', 'job_count', 'employer_created',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'employer_created']

    def get_staff_user_ids(self, obj):
        return company_staff_user_ids_for_api(obj)
    
    def get_logo(self, obj):
        from jobs.logo_url import resolved_company_logo_url

        return resolved_company_logo_url(obj, self.context.get("request"))

    def get_employer_logo(self, obj):
        if not getattr(obj, "employer_logo", None):
            return None
        url = obj.employer_logo.url
        if self.context.get("request") is not None and url.startswith("/"):
            return self.context["request"].build_absolute_uri(url)
        return url
    
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
    industries = IndustrySerializer(many=True, read_only=True)

    class Meta:
        model = Company
        fields = ["id", "name", "domain", "logo", "platform", "industries", "jobs"]
    
    def get_logo(self, obj):
        from jobs.logo_url import resolved_company_logo_url

        return resolved_company_logo_url(obj, self.context.get("request"))
    
    def get_jobs(self, obj):
        # Filter only active jobs and serialize them
        active_jobs = obj.jobs.filter(is_active=True)
        return NestedJobSerializer(active_jobs, many=True, context=self.context).data
    
    def to_representation(self, instance):
        """Ensure domain is empty string instead of None"""
        representation = super().to_representation(instance)
        if representation.get('domain') is None:
            representation['domain'] = ''
        return representation


class EmployerJobCreateSerializer(serializers.Serializer):
    """Payload for employer-posted jobs (enrichment runs on save)."""

    title = serializers.CharField(max_length=500)
    company = serializers.CharField(max_length=200)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    work_mode = serializers.ChoiceField(
        choices=["remote", "hybrid", "onsite", "on-site", "unknown"],
    )
    apply_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    is_active = serializers.BooleanField(default=True)
    full_description = serializers.CharField()
    salary = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class EmployerJobUpdateSerializer(serializers.Serializer):
    """Partial update: all employer-editable job fields (PATCH/POST body)."""

    title = serializers.CharField(max_length=500, required=False)
    company = serializers.CharField(max_length=200, required=False)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    location_country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    workplace_type = serializers.CharField(max_length=50, required=False, allow_blank=True)
    work_mode = serializers.ChoiceField(
        choices=["remote", "hybrid", "onsite", "on-site", "unknown"],
        required=False,
    )
    apply_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    # Main body text (same as create). Alias `description` for API ergonomics.
    full_description = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    salary = serializers.CharField(max_length=500, required=False, allow_blank=True)
    benefits = serializers.CharField(required=False, allow_blank=True)
    responsibilities = serializers.CharField(required=False, allow_blank=True)
    qualifications = serializers.CharField(required=False, allow_blank=True)
    industry_tags = serializers.CharField(required=False, allow_blank=True)
    posted_at = serializers.DateTimeField(required=False, allow_null=True)
    skills_required = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=True),
        required=False,
    )
    skills_preferred = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=True),
        required=False,
    )
    seniority = serializers.ChoiceField(
        choices=[c[0] for c in SENIORITY_CHOICES],
        required=False,
    )
    min_years_experience = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    visa_sponsorship = serializers.ChoiceField(
        choices=[c[0] for c in VISA_SPONSORSHIP_CHOICES],
        required=False,
    )
    work_authorization_required = serializers.ChoiceField(
        choices=[c[0] for c in WORK_AUTH_CHOICES],
        required=False,
    )


class EmployerCompanyWriteSerializer(serializers.ModelSerializer):
    """Create/update company via employer API. Staff links: POST/PATCH /api/employer/staff-memberships/."""

    employer_logo = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Multipart file field; use multipart/form-data with input key employer_logo.",
    )
    # Backward-compatible alias for clients still sending logo_upload.
    logo_upload = serializers.ImageField(
        source="employer_logo",
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Alias of employer_logo.",
    )

    industry_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
    )
    industry_names = serializers.ListField(
        child=serializers.CharField(max_length=200),
        required=False,
        write_only=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Logo-only multipart PATCH/PUT often omits other fields; `name` must stay required on create.
        if self.instance is not None:
            self.fields["name"].required = False

    class Meta:
        model = Company
        fields = [
            "name",
            "domain",
            "logo",
            "platform",
            "description",
            "website",
            "founded_date",
            "employees_count",
            "social_links",
            "additional_details",
            "company_email",
            "employer_logo",
            "logo_upload",
            "industry_ids",
            "industry_names",
        ]

    def validate_employer_logo(self, value):
        if value is None:
            return value
        max_bytes = 5 * 1024 * 1024
        if getattr(value, "size", 0) > max_bytes:
            raise serializers.ValidationError("Image must be <= 5MB.")
        return value

    @staticmethod
    def _apply_industries(company: Company, ids: list[int] | None, names: list[str] | None) -> None:
        pks: set[int] = set()
        if ids is not None:
            pks.update(ids)
        if names:
            for n in names:
                n = (n or "").strip()
                if n:
                    obj, _ = Industry.objects.get_or_create(name=n)
                    pks.add(obj.pk)
        company.industries.set(Industry.objects.filter(pk__in=pks))

    def create(self, validated_data):
        industry_ids = validated_data.pop("industry_ids", None)
        industry_names = validated_data.pop("industry_names", None)
        if not validated_data.get("name"):
            raise serializers.ValidationError({"name": "This field is required."})
        validated_data["employer_created"] = True
        company = Company.objects.create(**validated_data)
        if industry_ids is not None or industry_names is not None:
            self._apply_industries(company, industry_ids, industry_names)
        return company

    def update(self, instance, validated_data):
        if "employer_logo" in validated_data:
            incoming_logo = validated_data.get("employer_logo")
            if instance.employer_logo:
                instance.employer_logo.delete(save=False)
            validated_data["employer_logo"] = incoming_logo or None
        industry_ids = validated_data.pop("industry_ids", serializers.empty)
        industry_names = validated_data.pop("industry_names", serializers.empty)
        company = super().update(instance, validated_data)
        if "industry_ids" in self.initial_data or "industry_names" in self.initial_data:
            ids = None if industry_ids is serializers.empty else industry_ids
            names = None if industry_names is serializers.empty else industry_names
            self._apply_industries(company, ids, names)
        return company


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
            "salary": getattr(job, "salary", None),
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