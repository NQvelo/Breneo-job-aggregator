from rest_framework import serializers

from .models import JobApplicantCvView


class JobApplicantCvViewSerializer(serializers.ModelSerializer):
    job_title = serializers.CharField(source="job.title", read_only=True)
    company_id = serializers.IntegerField(source="job.company_id", read_only=True)
    company_name = serializers.CharField(source="job.company.name", read_only=True)

    class Meta:
        model = JobApplicantCvView
        fields = [
            "id",
            "job_id",
            "job_title",
            "company_id",
            "company_name",
            "application_id",
            "applicant_user_id",
            "viewer_user_id",
            "first_viewed_at",
            "last_viewed_at",
            "view_count",
            "applicant_acknowledged_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class EmployerCvViewWriteSerializer(serializers.Serializer):
    applicant_user_id = serializers.CharField(max_length=255)
    viewer_user_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    view_count = serializers.IntegerField(min_value=1, required=False)
    first_viewed_at = serializers.DateTimeField(required=False)
    last_viewed_at = serializers.DateTimeField(required=False)

    def validate_applicant_user_id(self, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("This field may not be blank.")
        return v

    def validate_viewer_user_id(self, value: str) -> str:
        return (value or "").strip()


class EmployerCvViewUpdateSerializer(serializers.Serializer):
    viewer_user_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    view_count = serializers.IntegerField(min_value=1, required=False)
    first_viewed_at = serializers.DateTimeField(required=False)
    last_viewed_at = serializers.DateTimeField(required=False)

    def validate_viewer_user_id(self, value: str) -> str:
        return (value or "").strip()


class ApplicantCvViewUpdateSerializer(serializers.Serializer):
    """Applicant may only acknowledge (or clear acknowledgement)."""

    applicant_acknowledged_at = serializers.DateTimeField(required=False, allow_null=True)
    acknowledge = serializers.BooleanField(required=False)

    def validate(self, attrs):
        acknowledge = attrs.pop("acknowledge", None)
        if acknowledge is True:
            from django.utils import timezone

            attrs["applicant_acknowledged_at"] = timezone.now()
        elif acknowledge is False:
            attrs["applicant_acknowledged_at"] = None
        if not attrs:
            raise serializers.ValidationError(
                "Provide applicant_acknowledged_at or acknowledge (true/false)."
            )
        return attrs
