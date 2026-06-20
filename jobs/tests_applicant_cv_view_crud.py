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
class ApplicantCvViewCrudAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.applicant_id = "applicant-user-42"
        self.employer_id = "employer-staff-7"
        self.company = Company.objects.create(name="Cv CRUD Co", employer_created=True)
        self.job = Job.objects.create(
            title="Backend Engineer",
            company=self.company,
            platform="employer",
            external_job_id="cv-crud-1",
            is_active=True,
        )
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.employer_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        self.application = JobApplication.objects.create(
            external_user_id=self.applicant_id,
            job=self.job,
            applied_at=timezone.now(),
        )
        self.cv_row = JobApplicantCvView.objects.create(
            job=self.job,
            application=self.application,
            applicant_user_id=self.applicant_id,
            viewer_user_id=self.employer_id,
            first_viewed_at=timezone.now(),
            last_viewed_at=timezone.now(),
            view_count=1,
        )

    def test_employer_lists_cv_views(self):
        url = reverse("employer_job_cv_views", kwargs={"job_id": self.job.id})
        response = self.client.get(
            f"{url}?external_user_id={self.employer_id}",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["applicant_user_id"], self.applicant_id)

    def test_employer_creates_cv_view(self):
        other_applicant = "other-applicant-99"
        JobApplication.objects.create(
            external_user_id=other_applicant,
            job=self.job,
            applied_at=timezone.now(),
        )
        url = reverse("employer_job_cv_views", kwargs={"job_id": self.job.id})
        response = self.client.post(
            f"{url}?external_user_id={self.employer_id}",
            {"applicant_user_id": other_applicant, "viewer_user_id": self.employer_id},
            format="json",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            JobApplicantCvView.objects.filter(
                job=self.job,
                applicant_user_id=other_applicant,
            ).exists()
        )

    def test_employer_updates_cv_view(self):
        url = reverse(
            "employer_job_cv_view_detail",
            kwargs={"job_id": self.job.id, "cv_view_id": self.cv_row.id},
        )
        response = self.client.patch(
            f"{url}?external_user_id={self.employer_id}",
            {"view_count": 5},
            format="json",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.cv_row.refresh_from_db()
        self.assertEqual(self.cv_row.view_count, 5)

    def test_employer_deletes_cv_view(self):
        url = reverse(
            "employer_job_cv_view_detail",
            kwargs={"job_id": self.job.id, "cv_view_id": self.cv_row.id},
        )
        response = self.client.delete(
            f"{url}?external_user_id={self.employer_id}",
            HTTP_X_EMPLOYER_KEY="test-employer-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(JobApplicantCvView.objects.filter(pk=self.cv_row.id).exists())

    def test_applicant_lists_cv_views(self):
        url = reverse("user_cv_views")
        response = self.client.get(
            url,
            {"external_user_id": self.applicant_id},
            HTTP_X_APPLICATION_KEY="test-application-api-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)

    def test_applicant_acknowledges_cv_view(self):
        url = reverse("user_cv_view_detail", kwargs={"cv_view_id": self.cv_row.id})
        response = self.client.patch(
            url,
            {"external_user_id": self.applicant_id, "acknowledge": True},
            format="json",
            HTTP_X_APPLICATION_KEY="test-application-api-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.cv_row.refresh_from_db()
        self.assertIsNotNone(self.cv_row.applicant_acknowledged_at)

    def test_applicant_cannot_access_other_users_cv_view(self):
        url = reverse("user_cv_view_detail", kwargs={"cv_view_id": self.cv_row.id})
        response = self.client.get(
            url,
            {"external_user_id": "someone-else"},
            HTTP_X_APPLICATION_KEY="test-application-api-secret",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
