"""Persistence for employer CV/profile view tracking."""

from __future__ import annotations

from django.db.models import Max, Min, Sum
from django.utils import timezone

from ..models import JobApplicantCvView, JobApplication


class ApplicantCvViewRepository:
    def queryset_for_job(self, job_id: int):
        return JobApplicantCvView.objects.filter(job_id=job_id).select_related(
            "job",
            "job__company",
            "application",
        )

    def queryset_for_applicant(self, applicant_user_id: str):
        return JobApplicantCvView.objects.filter(
            applicant_user_id=applicant_user_id,
        ).select_related("job", "job__company", "application")

    def get_by_id(self, cv_view_id: int) -> JobApplicantCvView | None:
        return (
            JobApplicantCvView.objects.select_related(
                "job",
                "job__company",
                "application",
            )
            .filter(pk=cv_view_id)
            .first()
        )

    def get_active_application(self, applicant_user_id: str, job_id: int) -> JobApplication | None:
        return (
            JobApplication.objects.filter(
                external_user_id=applicant_user_id,
                job_id=job_id,
                withdrawn_at__isnull=True,
            )
            .select_related("job")
            .first()
        )

    def record_view(
        self,
        *,
        job_id: int,
        applicant_user_id: str,
        viewer_user_id: str,
        application: JobApplication | None = None,
    ) -> JobApplicantCvView:
        now = timezone.now()
        row, created = JobApplicantCvView.objects.get_or_create(
            job_id=job_id,
            applicant_user_id=applicant_user_id,
            viewer_user_id=viewer_user_id,
            defaults={
                "application": application,
                "first_viewed_at": now,
                "last_viewed_at": now,
                "view_count": 1,
            },
        )
        if created:
            return row

        row.view_count += 1
        row.last_viewed_at = now
        if application is not None and row.application_id is None:
            row.application = application
        row.save(update_fields=["view_count", "last_viewed_at", "application", "updated_at"])
        return row

    def create_view(
        self,
        *,
        job_id: int,
        applicant_user_id: str,
        viewer_user_id: str,
        application: JobApplication | None,
        view_count: int = 1,
        first_viewed_at=None,
        last_viewed_at=None,
    ) -> JobApplicantCvView:
        now = timezone.now()
        return JobApplicantCvView.objects.create(
            job_id=job_id,
            applicant_user_id=applicant_user_id,
            viewer_user_id=viewer_user_id,
            application=application,
            view_count=max(1, view_count),
            first_viewed_at=first_viewed_at or now,
            last_viewed_at=last_viewed_at or first_viewed_at or now,
        )

    def update_view(self, row: JobApplicantCvView, **fields) -> JobApplicantCvView:
        update_fields = []
        for key, value in fields.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
                update_fields.append(key)
        if update_fields:
            row.save(update_fields=[*update_fields, "updated_at"])
        return row

    def delete_view(self, row: JobApplicantCvView) -> None:
        row.delete()

    def exists_for_triple(
        self,
        job_id: int,
        applicant_user_id: str,
        viewer_user_id: str,
        *,
        exclude_id: int | None = None,
    ) -> bool:
        qs = JobApplicantCvView.objects.filter(
            job_id=job_id,
            applicant_user_id=applicant_user_id,
            viewer_user_id=viewer_user_id,
        )
        if exclude_id is not None:
            qs = qs.exclude(pk=exclude_id)
        return qs.exists()

    def aggregate_for_job_applicants(
        self,
        job_id: int,
        applicant_user_ids: list[str],
    ) -> dict[str, dict]:
        if not applicant_user_ids:
            return {}

        rows = (
            JobApplicantCvView.objects.filter(
                job_id=job_id,
                applicant_user_id__in=applicant_user_ids,
            )
            .values("applicant_user_id")
            .annotate(
                first_viewed_at=Min("first_viewed_at"),
                last_viewed_at=Max("last_viewed_at"),
                view_count=Sum("view_count"),
            )
        )
        return {
            row["applicant_user_id"]: {
                "employer_viewed_cv": True,
                "employer_first_viewed_at": row["first_viewed_at"],
                "employer_last_viewed_at": row["last_viewed_at"],
                "employer_cv_view_count": row["view_count"] or 0,
            }
            for row in rows
        }

    def aggregate_for_job_applicants_by_viewer(
        self,
        job_id: int,
        applicant_user_ids: list[str],
        viewer_user_id: str,
    ) -> dict[str, dict]:
        if not applicant_user_ids or not viewer_user_id:
            return {}

        rows = JobApplicantCvView.objects.filter(
            job_id=job_id,
            applicant_user_id__in=applicant_user_ids,
            viewer_user_id=viewer_user_id,
        )
        return {
            row.applicant_user_id: {
                "cv_viewed_by_me": True,
                "cv_my_first_viewed_at": row.first_viewed_at,
                "cv_my_last_viewed_at": row.last_viewed_at,
                "cv_my_view_count": row.view_count,
            }
            for row in rows
        }

    def empty_summary(self) -> dict:
        return {
            "employer_viewed_cv": False,
            "employer_first_viewed_at": None,
            "employer_last_viewed_at": None,
            "employer_cv_view_count": 0,
        }

    def empty_viewer_summary(self) -> dict:
        return {
            "cv_viewed_by_me": False,
            "cv_my_first_viewed_at": None,
            "cv_my_last_viewed_at": None,
            "cv_my_view_count": 0,
        }
