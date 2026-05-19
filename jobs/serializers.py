
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from rest_framework import serializers
from .models import (
    Job,
    Company,
    CompanyStaffMembership,
    Industry,
    JobApplication,
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


class JobApplyEligibilityMixin(serializers.ModelSerializer):
    """
    Frontend: if supports_in_app_apply is true, show Breneo Apply button.
    If false, keep the existing external apply link/button (apply_url) unchanged.
    """

    supports_in_app_apply = serializers.SerializerMethodField()

    class Meta:
        abstract = True

    def get_supports_in_app_apply(self, obj) -> bool:
        from .job_apply_eligibility import job_supports_in_app_apply

        return job_supports_in_app_apply(obj)


class JobCityCountryFieldsMixin(serializers.ModelSerializer):
    """City/country mirror location/location_country for stable public API field names."""

    city = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()

    class Meta:
        abstract = True

    def get_city(self, obj):
        v = getattr(obj, "location", None)
        return "" if v is None else v

    def get_country(self, obj):
        v = getattr(obj, "location_country", None)
        return "" if v is None else v


class JobSerializer(JobApplyEligibilityMixin, JobCityCountryFieldsMixin, DynamicFieldsModelSerializer):
    company_logo = serializers.SerializerMethodField()
    description_short = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'company', 'company_logo', 'location', 'location_country', 'city', 'country',
            'workplace_type', 'work_mode', 'skills_required', 'skills_preferred', 'tech_stack', 'tech_stack_candidates',
            'seniority', 'role_category', 'min_years_experience', 'languages_required', 'industry_tags',
            'visa_sponsorship', 'work_authorization_required',
            'data_completeness_score', 'description', 'description_short', 'responsibilities', 'qualifications',
            'salary', 'apply_url', 'platform', 'external_job_id', 'posted_at', 'fetched_at', 'is_active',
            'supports_in_app_apply', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at', 'supports_in_app_apply']

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
    user_id = serializers.CharField(source="external_user_id", read_only=True)
    user_email = serializers.CharField(source="external_user_email", read_only=True)
    user_name = serializers.CharField(source="external_user_name", read_only=True)
    user_surname = serializers.CharField(source="external_user_surname", read_only=True)

    class Meta:
        model = CompanyStaffMembership
        fields = [
            "id",
            "company_id",
            "external_user_id",
            "external_user_email",
            "external_user_name",
            "external_user_surname",
            "user_id",
            "user_email",
            "user_name",
            "user_surname",
            "is_admin",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_external_user_id(self, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("This field may not be blank.")
        return v

    def validate_is_admin(self, value: bool) -> bool:
        instance = self.instance
        if instance is None:
            return value

        request = self.context.get("request")
        from .breneo_user import external_user_id_from_request

        requester_id = external_user_id_from_request(request) if request else ""
        new_value = value
        if new_value == instance.is_admin:
            return value

        from .services.staff_memberships import check_can_change_admin_flag

        err = check_can_change_admin_flag(
            company=instance.company,
            requester_user_id=requester_id,
            instance=instance,
            new_is_admin=new_value,
        )
        if err:
            raise serializers.ValidationError(err)
        return value

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

    def create(self, validated_data):
        request = self.context.get("request")
        company = validated_data["company"]
        external_user_id = validated_data["external_user_id"]
        requested_admin = validated_data.pop("is_admin", False)

        from .services.staff_memberships import (
            resolve_is_admin_on_create,
            staff_profile_create_kwargs,
        )

        profile_kwargs = staff_profile_create_kwargs(request, external_user_id) if request else {}
        validated_data.update(profile_kwargs)
        validated_data["is_admin"] = resolve_is_admin_on_create(company, requested_admin)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context.get("request")
        external_user_id = validated_data.get("external_user_id", instance.external_user_id)

        if request:
            from .services.staff_memberships import (
                merge_staff_profile_kwargs,
                staff_profile_create_kwargs,
            )

            incoming = staff_profile_create_kwargs(request, external_user_id)
            validated_data.update(merge_staff_profile_kwargs(instance, incoming))

        return super().update(instance, validated_data)


class CompanyInfoSerializer(DynamicFieldsModelSerializer):
    """Serializer for company information nested within job responses"""
    logo = serializers.SerializerMethodField()
    industries = IndustrySerializer(many=True, read_only=True)
    staff_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'domain', 'logo', 'platform', 'description', 'website',
            'founded_date', 'employees_count', 'social_links', 'additional_details',
            'industries', 'company_email', 'staff_user_ids', 'employer_created',
        ]
        read_only_fields = ['id', 'employer_created']

    def get_staff_user_ids(self, obj):
        return company_staff_user_ids_for_api(obj)
    
    def get_logo(self, obj):
        from jobs.logo_url import resolved_company_logo_url

        return resolved_company_logo_url(obj, self.context.get("request"))

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


class NestedJobSerializer(JobApplyEligibilityMixin, JobCityCountryFieldsMixin, DynamicFieldsModelSerializer):
    """Serializer for jobs nested within company data"""
    company = CompanyInfoSerializer(read_only=True)
    description_short = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'company', 'location', 'location_country', 'city', 'country',
            'workplace_type', 'work_mode', 'skills_required', 'skills_preferred', 'tech_stack', 'tech_stack_candidates',
            'seniority', 'role_category', 'min_years_experience', 'languages_required', 'industry_tags',
            'visa_sponsorship', 'work_authorization_required', 'data_completeness_score',
            'description', 'description_short', 'responsibilities', 'qualifications',
            'salary', 'apply_url', 'platform', 'external_job_id',
            'posted_at', 'fetched_at', 'is_active', 'supports_in_app_apply', 'raw',
        ]
        read_only_fields = ['id', 'fetched_at', 'supports_in_app_apply']

    def get_description_short(self, obj):
        return obj.get_description_short(max_lines=4, max_chars=400)


class CompanyDetailSerializer(DynamicFieldsModelSerializer):
    """Serializer for company details with all fields"""
    logo = serializers.SerializerMethodField()
    job_count = serializers.SerializerMethodField()
    industries = IndustrySerializer(many=True, read_only=True)
    staff_user_ids = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'domain', 'logo', 'platform', 'description', 'website',
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
    city = serializers.CharField(max_length=200, required=False, allow_blank=True)
    work_mode = serializers.ChoiceField(
        choices=["remote", "hybrid", "onsite", "on-site", "unknown"],
    )
    apply_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    is_active = serializers.BooleanField(default=True)
    full_description = serializers.CharField()
    salary = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ParseJobDescriptionSerializer(serializers.Serializer):
    """
    POST /api/jobs/parse-description — Gemini parses employer-entered description text.
    `source` must be employer_manual (blocks accidental use for non-manual flows).
    """

    description = serializers.CharField(min_length=1, max_length=500_000, trim_whitespace=True)
    source = serializers.ChoiceField(
        choices=["employer_manual"],
        default="employer_manual",
    )


class EmployerJobUpdateSerializer(serializers.Serializer):
    """Partial update: all employer-editable job fields (PATCH/POST body)."""

    title = serializers.CharField(max_length=500, required=False)
    company = serializers.CharField(max_length=200, required=False)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    city = serializers.CharField(max_length=200, required=False, allow_blank=True)
    location_country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    country = serializers.CharField(max_length=100, required=False, allow_blank=True)
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

    # Override model URLField: multipart clients often send "null"/"" for logo and break strict URL validation.
    logo = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=2048,
        help_text="External logo URL (scraped/fetched). Omit or leave empty when using logo_upload file.",
    )

    logo_upload = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Multipart file field; use multipart/form-data with input key logo_upload.",
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

    def validate_logo(self, value):
        if value is None:
            return None
        s = str(value).strip()
        if not s or s.lower() in ("null", "undefined", "none", "nan"):
            return None
        try:
            URLValidator()(s)
        except DjangoValidationError as exc:
            raise serializers.ValidationError("Enter a valid URL.") from exc
        return s

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
            "logo_upload",
            "industry_ids",
            "industry_names",
        ]

    def validate_logo_upload(self, value):
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
        if "logo_upload" in validated_data:
            incoming_logo = validated_data.get("logo_upload")
            if instance.logo_upload:
                instance.logo_upload.delete(save=False)
            validated_data["logo_upload"] = incoming_logo or None
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


class JobApplicationJobSummarySerializer(
    JobApplyEligibilityMixin, JobCityCountryFieldsMixin, serializers.ModelSerializer
):
    """Nested job details for application list responses."""

    company_name = serializers.CharField(source="company.name", read_only=True)
    company_logo = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "title",
            "company",
            "company_name",
            "company_logo",
            "location",
            "location_country",
            "city",
            "country",
            "workplace_type",
            "work_mode",
            "seniority",
            "salary",
            "apply_url",
            "platform",
            "posted_at",
            "is_active",
            "supports_in_app_apply",
        ]
        read_only_fields = ["supports_in_app_apply"]

    def get_company_logo(self, obj):
        from jobs.logo_url import resolved_company_logo_url

        if obj.company:
            return resolved_company_logo_url(obj.company, self.context.get("request"))
        return None


class JobApplicationUserFieldsMixin(serializers.Serializer):
    """
    Always expose applicant identity in API responses (both naming styles).
    Matches BFF payload: external_user_id, external_user_email, external_user_name, external_user_surname.
    """

    external_user_id = serializers.SerializerMethodField()
    external_user_email = serializers.SerializerMethodField()
    external_user_name = serializers.SerializerMethodField()
    external_user_surname = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    user_surname = serializers.SerializerMethodField()

    def _applicant_identity(self, obj) -> dict[str, str]:
        return {
            "external_user_id": obj.external_user_id or "",
            "external_user_email": obj.external_user_email or "",
            "external_user_name": obj.external_user_name or "",
            "external_user_surname": obj.external_user_surname or "",
        }

    def get_external_user_id(self, obj) -> str:
        return self._applicant_identity(obj)["external_user_id"]

    def get_external_user_email(self, obj) -> str:
        return self._applicant_identity(obj)["external_user_email"]

    def get_external_user_name(self, obj) -> str:
        return self._applicant_identity(obj)["external_user_name"]

    def get_external_user_surname(self, obj) -> str:
        return self._applicant_identity(obj)["external_user_surname"]

    def get_user_id(self, obj) -> str:
        return self.get_external_user_id(obj)

    def get_user_email(self, obj) -> str:
        return self.get_external_user_email(obj)

    def get_user_name(self, obj) -> str:
        return self.get_external_user_name(obj)

    def get_user_surname(self, obj) -> str:
        return self.get_external_user_surname(obj)


class JobApplicationSerializer(JobApplicationUserFieldsMixin, serializers.ModelSerializer):
    """User-facing application record (includes nested job)."""

    job_id = serializers.IntegerField(source="job.id", read_only=True)
    job = JobApplicationJobSummarySerializer(read_only=True)
    is_withdrawn = serializers.BooleanField(read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "external_user_id",
            "external_user_email",
            "external_user_name",
            "external_user_surname",
            "user_id",
            "user_email",
            "user_name",
            "user_surname",
            "job_id",
            "job",
            "applied_at",
            "status",
            "is_withdrawn",
            "withdrawn_at",
            "created_at",
            "updated_at",
        ]


class JobApplicantSerializer(JobApplicationUserFieldsMixin, serializers.ModelSerializer):
    """Employer view: applicant with stored contact fields + optional breneo profile merge."""

    job_id = serializers.IntegerField(source="job.id", read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "external_user_id",
            "external_user_email",
            "external_user_name",
            "external_user_surname",
            "user_id",
            "user_email",
            "user_name",
            "user_surname",
            "user",
            "job_id",
            "applied_at",
            "status",
            "created_at",
            "updated_at",
        ]

    def get_user(self, obj):
        identity = self._applicant_identity(obj)
        stored = {
            "id": identity["external_user_id"],
            "email": identity["external_user_email"],
            "first_name": identity["external_user_name"],
            "last_name": identity["external_user_surname"],
            "firstName": identity["external_user_name"],
            "lastName": identity["external_user_surname"],
            "name": identity["external_user_name"],
            "surname": identity["external_user_surname"],
            "external_user_id": identity["external_user_id"],
            "external_user_email": identity["external_user_email"],
            "external_user_name": identity["external_user_name"],
            "external_user_surname": identity["external_user_surname"],
        }
        profiles = self.context.get("user_profiles") or {}
        remote = profiles.get(obj.external_user_id) or {}
        return {**remote, **stored}