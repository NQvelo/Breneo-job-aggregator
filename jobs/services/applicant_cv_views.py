"""Business logic for employer CV view tracking."""

from __future__ import annotations

import logging

from django.utils import timezone

from ..application_exceptions import (
    ApplicationNotFoundError,
    CvViewAlreadyExistsError,
    CvViewNotFoundError,
    ForbiddenJobAccessError,
    JobNotFoundError,
)
from ..models import CompanyStaffMembership, JobApplicantCvView
from ..repositories.applicant_cv_views import ApplicantCvViewRepository
from ..repositories.job_applications import JobApplicationRepository

logger = logging.getLogger(__name__)


class ApplicantCvViewService:
    def __init__(
        self,
        cv_repo: ApplicantCvViewRepository | None = None,
        application_repo: JobApplicationRepository | None = None,
    ):
        self.cv_repo = cv_repo or ApplicantCvViewRepository()
        self.application_repo = application_repo or JobApplicationRepository()

    def _get_job(self, job_id: int):
        job = self.application_repo.get_job(job_id)
        if not job:
            raise JobNotFoundError("Job not found")
        return job

    def _assert_viewer_access(self, job, viewer_user_id: str) -> None:
        if not viewer_user_id:
            return
        if not CompanyStaffMembership.objects.filter(
            company=job.company,
            external_user_id=viewer_user_id,
            status__in=CompanyStaffMembership.access_statuses(),
        ).exists():
            raise ForbiddenJobAccessError("Not authorized for this company's jobs.")

    def _assert_applicant_access(self, row: JobApplicantCvView, applicant_user_id: str) -> None:
        if row.applicant_user_id != applicant_user_id:
            raise ForbiddenJobAccessError("Not authorized to access this CV view record.")

    def list_for_job(self, job_id: int, *, requester_user_id: str | None = None):
        job = self._get_job(job_id)
        self._assert_viewer_access(job, requester_user_id or "")
        return self.cv_repo.queryset_for_job(job_id).order_by("-last_viewed_at", "-id")

    def list_for_applicant(self, applicant_user_id: str):
        return self.cv_repo.queryset_for_applicant(applicant_user_id).order_by(
            "-last_viewed_at",
            "-id",
        )

    def get_for_employer(self, job_id: int, cv_view_id: int, *, requester_user_id: str):
        job = self._get_job(job_id)
        self._assert_viewer_access(job, requester_user_id)
        row = self.cv_repo.get_by_id(cv_view_id)
        if not row or row.job_id != job_id:
            raise CvViewNotFoundError("CV view record not found")
        return row

    def get_for_applicant(self, cv_view_id: int, *, applicant_user_id: str):
        row = self.cv_repo.get_by_id(cv_view_id)
        if not row:
            raise CvViewNotFoundError("CV view record not found")
        self._assert_applicant_access(row, applicant_user_id)
        return row

    def record_cv_view(self, job_id: int, applicant_user_id: str, viewer_user_id: str):
        job = self._get_job(job_id)
        self._assert_viewer_access(job, viewer_user_id)

        application = self.cv_repo.get_active_application(applicant_user_id, job_id)
        if not application:
            raise ApplicationNotFoundError("Applicant has no active application for this job.")

        row = self.cv_repo.record_view(
            job_id=job_id,
            applicant_user_id=applicant_user_id,
            viewer_user_id=viewer_user_id,
            application=application,
        )
        logger.info(
            "Employer %s viewed CV of applicant %s for job %s (count=%s)",
            viewer_user_id,
            applicant_user_id,
            job_id,
            row.view_count,
        )
        return row

    def create_cv_view(
        self,
        job_id: int,
        *,
        applicant_user_id: str,
        viewer_user_id: str,
        requester_user_id: str,
        view_count: int = 1,
        first_viewed_at=None,
        last_viewed_at=None,
    ):
        job = self._get_job(job_id)
        self._assert_viewer_access(job, requester_user_id)

        application = self.cv_repo.get_active_application(applicant_user_id, job_id)
        if not application:
            raise ApplicationNotFoundError("Applicant has no active application for this job.")

        if self.cv_repo.exists_for_triple(job_id, applicant_user_id, viewer_user_id):
            raise CvViewAlreadyExistsError(
                "A CV view record already exists for this job, applicant, and viewer."
            )

        return self.cv_repo.create_view(
            job_id=job_id,
            applicant_user_id=applicant_user_id,
            viewer_user_id=viewer_user_id,
            application=application,
            view_count=view_count,
            first_viewed_at=first_viewed_at,
            last_viewed_at=last_viewed_at,
        )

    def update_cv_view_employer(
        self,
        job_id: int,
        cv_view_id: int,
        *,
        requester_user_id: str,
        **fields,
    ):
        row = self.get_for_employer(job_id, cv_view_id, requester_user_id=requester_user_id)

        new_viewer = fields.get("viewer_user_id")
        if new_viewer and new_viewer != row.viewer_user_id:
            if self.cv_repo.exists_for_triple(
                job_id,
                row.applicant_user_id,
                new_viewer,
                exclude_id=row.pk,
            ):
                raise CvViewAlreadyExistsError(
                    "A CV view record already exists for this job, applicant, and viewer."
                )

        return self.cv_repo.update_view(row, **fields)

    def update_cv_view_applicant(
        self,
        cv_view_id: int,
        *,
        applicant_user_id: str,
        applicant_acknowledged_at=None,
    ):
        row = self.get_for_applicant(cv_view_id, applicant_user_id=applicant_user_id)
        return self.cv_repo.update_view(row, applicant_acknowledged_at=applicant_acknowledged_at)

    def acknowledge_cv_view(self, cv_view_id: int, *, applicant_user_id: str):
        return self.update_cv_view_applicant(
            cv_view_id,
            applicant_user_id=applicant_user_id,
            applicant_acknowledged_at=timezone.now(),
        )

    def delete_cv_view(self, job_id: int, cv_view_id: int, *, requester_user_id: str) -> None:
        row = self.get_for_employer(job_id, cv_view_id, requester_user_id=requester_user_id)
        self.cv_repo.delete_view(row)

    def summaries_for_applications(
        self,
        job_id: int,
        applicant_user_ids: list[str],
        *,
        viewer_user_id: str | None = None,
    ) -> dict[str, dict]:
        aggregate = self.cv_repo.aggregate_for_job_applicants(job_id, applicant_user_ids)
        viewer_map = (
            self.cv_repo.aggregate_for_job_applicants_by_viewer(
                job_id,
                applicant_user_ids,
                viewer_user_id,
            )
            if viewer_user_id
            else {}
        )

        result: dict[str, dict] = {}
        for applicant_id in applicant_user_ids:
            summary = aggregate.get(applicant_id) or self.cv_repo.empty_summary()
            viewer_summary = viewer_map.get(applicant_id) or self.cv_repo.empty_viewer_summary()
            result[applicant_id] = {**summary, **viewer_summary}
        return result

    def summaries_for_application_list(
        self,
        applications,
        *,
        viewer_user_id: str | None = None,
    ) -> dict[str, dict]:
        by_job: dict[int, list[str]] = {}
        for app in applications:
            by_job.setdefault(app.job_id, []).append(app.external_user_id)

        flat: dict[str, dict] = {}
        for job_id, applicant_ids in by_job.items():
            unique_ids = list(dict.fromkeys(applicant_ids))
            for applicant_id, data in self.summaries_for_applications(
                job_id,
                unique_ids,
                viewer_user_id=viewer_user_id,
            ).items():
                flat[f"{job_id}:{applicant_id}"] = data
        return flat
