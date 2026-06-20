import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Company, CompanyStaffMembership, Job, JobApplication, JobApplicantCvView


@patch.dict(
    os.environ,
    {
        "APPLICATION_API_SECRET": "test-application-api-secret",
        "EMPLOYER_POST_SECRET": "test-employer-secret",
    },
)
class JobApplicantCvViewAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.applicant_id = "applicant-user-42"
        self.employer_id = "employer-staff-7"
        self.company = Company.objects.create(name="Cv View Co", employer_created=True)
        self.job = Job.objects.create(
            title="Backend Engineer",
            company=self.company,
            platform="employer",
            external_job_id="cv-view-job-1",
            is_active=True,
        )
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.employer_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        self.application = JobApplication.objects.create(
            external_user_id=self.applicant_id,
            external_user_email="applicant@example.com",
            job=self.job,
            applied_at=timezone.now(),
        )

    def _record_url(self):
        return reverse(
            "job_applicant_cv_view",
            kwargs={"job_id": self.job.id, "applicant_user_id": self.applicant_id},
        )

    def test_employer_records_cv_view(self):
        response = self.client.post(
            f"{self._record_url()}?external_user_id={self.employer_id}",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        row = JobApplicantCvView.objects.get(
            job=self.job,
            applicant_user_id=self.applicant_id,
            viewer_user_id=self.employer_id,
        )
        self.assertEqual(row.view_count, 1)

    def test_repeat_view_increments_count(self):
        url = f"{self._record_url()}?external_user_id={self.employer_id}"
        self.client.post(url, HTTP_X_EMPLOYER_KEY="test-employer-secret")
        self.client.post(url, HTTP_X_EMPLOYER_KEY="test-employer-secret")
        row = JobApplicantCvView.objects.get(job=self.job, applicant_user_id=self.applicant_id)
        self.assertEqual(row.view_count, 2)

    def test_applicant_sees_employer_viewed_on_my_applications(self):
        self.client.post(
            f"{self._record_url()}?external_user_id={self.employer_id}",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        response = self.client.get(
            reverse("user_applications"),
            {"external_user_id": self.applicant_id},
            HTTP_X_APPLICATION_KEY="test-application-api-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["data"]["items"][0]
        self.assertTrue(item["employer_viewed_cv"])
        self.assertEqual(item["employer_cv_view_count"], 1)

    def test_employer_applicants_list_includes_view_flags(self):
        self.client.post(
            f"{self._record_url()}?external_user_id={self.employer_id}",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        response = self.client.get(
            f"{reverse('job_applicants', kwargs={'job_id': self.job.id})}?external_user_id={self.employer_id}",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["data"]["items"][0]
        self.assertTrue(item["employer_viewed_cv"])
        self.assertTrue(item["cv_viewed_by_me"])

    def test_record_view_requires_active_application(self):
        self.application.withdrawn_at = timezone.now()
        self.application.save(update_fields=["withdrawn_at"])
        response = self.client.post(
            self._record_url(),
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_staff_cannot_record_view_when_scoped(self):
        response = self.client.post(
            f"{self._record_url()}?external_user_id=random-user",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
