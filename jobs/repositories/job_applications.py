"""Database queries for job applications."""

from __future__ import annotations

from django.db.models import QuerySet
from django.utils import timezone

from ..models import Job, JobApplication


class JobApplicationRepository:
    SORT_FIELDS = {
        "applied_at": "applied_at",
        "-applied_at": "-applied_at",
        "created_at": "created_at",
        "-created_at": "-created_at",
        "status": "status",
        "-status": "-status",
    }

    @staticmethod
    def active_applications() -> QuerySet[JobApplication]:
        return JobApplication.objects.filter(withdrawn_at__isnull=True)

    @staticmethod
    def get_job(job_id: int) -> Job | None:
        return Job.objects.filter(pk=job_id).select_related("company").first()

    @staticmethod
    def get_active_application(user_id: str, job_id: int) -> JobApplication | None:
        return (
            JobApplicationRepository.active_applications()
            .filter(external_user_id=user_id, job_id=job_id)
            .select_related("job", "job__company")
            .first()
        )

    @staticmethod
    def get_application_row(user_id: str, job_id: int) -> JobApplication | None:
        return (
            JobApplication.objects.filter(external_user_id=user_id, job_id=job_id)
            .select_related("job", "job__company")
            .first()
        )

    @staticmethod
    def list_for_user(user_id: str, sort: str = "-applied_at") -> QuerySet[JobApplication]:
        order = JobApplicationRepository.SORT_FIELDS.get(sort, "-applied_at")
        return (
            JobApplicationRepository.active_applications()
            .filter(external_user_id=user_id)
            .select_related("job", "job__company")
            .order_by(order, "-id")
        )

    @staticmethod
    def list_for_job(job_id: int, sort: str = "-applied_at") -> QuerySet[JobApplication]:
        order = JobApplicationRepository.SORT_FIELDS.get(sort, "-applied_at")
        return (
            JobApplicationRepository.active_applications()
            .filter(job_id=job_id)
            .select_related("job", "job__company")
            .order_by(order, "-id")
        )

    @staticmethod
    def create_application(user_id: str, job: Job, applied_at=None) -> JobApplication:
        return JobApplication.objects.create(
            external_user_id=user_id,
            job=job,
            applied_at=applied_at or timezone.now(),
            status="applied",
        )

    @staticmethod
    def reactivate(application: JobApplication) -> JobApplication:
        application.withdrawn_at = None
        application.status = "applied"
        application.applied_at = timezone.now()
        application.save(update_fields=["withdrawn_at", "status", "applied_at", "updated_at"])
        return application

    @staticmethod
    def withdraw(application: JobApplication) -> JobApplication:
        application.withdrawn_at = timezone.now()
        application.save(update_fields=["withdrawn_at", "updated_at"])
        return application
