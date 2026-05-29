"""Business logic for job applications."""

from __future__ import annotations

import logging

from django.db import IntegrityError

from ..application_exceptions import (
    AlreadyAppliedError,
    ApplicationNotFoundError,
    EmployerJobOnlyError,
    ForbiddenJobAccessError,
    JobNotAcceptingApplicationsError,
    JobNotFoundError,
)
from ..applicant_profile import ApplicantProfile, enrich_applicant_profile
from ..job_apply_eligibility import job_supports_in_app_apply
from ..models import CompanyStaffMembership, JobApplication
from ..repositories.job_applications import JobApplicationRepository
from .breneo_user_client import fetch_user_profiles

logger = logging.getLogger(__name__)


class JobApplicationService:
    def __init__(self, repository: JobApplicationRepository | None = None):
        self.repo = repository or JobApplicationRepository()

    def apply(self, profile: ApplicantProfile, job_id: int) -> JobApplication:
        profile = enrich_applicant_profile(profile)
        user_id = profile.user_id
        job = self.repo.get_job(job_id)
        if not job:
            raise JobNotFoundError("Job not found")
        if not job.is_active:
            raise JobNotAcceptingApplicationsError("Job is not accepting applications")
        if not job_supports_in_app_apply(job):
            raise EmployerJobOnlyError(
                "In-app apply is only available for jobs posted on the Breneo platform. "
                "Use the external apply link for this job."
            )

        existing = self.repo.get_application_row(user_id, job_id)
        if existing:
            if existing.withdrawn_at is None:
                raise AlreadyAppliedError("You have already applied to this job.")
            return self.repo.reactivate(existing, profile)

        try:
            application = self.repo.create_application(profile, job)
            logger.info("User %s applied to job %s", user_id, job_id)
            return application
        except IntegrityError:
            raise AlreadyAppliedError("You have already applied to this job.") from None

    def withdraw(self, user_id: str, job_id: int) -> JobApplication:
        application = self.repo.get_active_application(user_id, job_id)
        if not application:
            raise ApplicationNotFoundError("No active application found for this job.")
        withdrawn = self.repo.withdraw(application)
        logger.info("User %s withdrew application for job %s", user_id, job_id)
        return withdrawn

    def list_user_applications(self, user_id: str, sort: str = "-applied_at"):
        return self.repo.list_for_user(user_id, sort=sort)

    def list_job_applicants(
        self,
        job_id: int,
        *,
        requester_user_id: str | None = None,
        sort: str = "-applied_at",
        auth_token: str | None = None,
    ):
        job = self.repo.get_job(job_id)
        if not job:
            raise JobNotFoundError("Job not found")
        if requester_user_id and not CompanyStaffMembership.objects.filter(
            company=job.company,
            external_user_id=requester_user_id,
            status__in=CompanyStaffMembership.access_statuses(),
        ).exists():
            raise ForbiddenJobAccessError("Not authorized for this company's jobs.")

        applications = list(self.repo.list_for_job(job_id, sort=sort))
        user_ids = [a.external_user_id for a in applications]
        profiles = fetch_user_profiles(user_ids, auth_token=auth_token)
        return applications, profiles, job
