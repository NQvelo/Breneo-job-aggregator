import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import Company, CompanyStaffMembership, Job, JobApplication


@patch.dict(os.environ, {"EMPLOYER_POST_SECRET": "test-employer-secret"})
class JobApplicationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_id = "breneo-user-42"
        self.other_user_id = "breneo-user-99"
        self.company = Company.objects.create(name="Apply Co", employer_created=True)
        self.job = Job.objects.create(
            title="Backend Engineer",
            company=self.company,
            platform="employer",
            external_job_id="employer-test-1",
            is_active=True,
        )
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.user_id,
        )

    def test_apply_creates_application(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(
            url,
            {"user_id": self.user_id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user_id"], self.user_id)
        self.assertEqual(response.data["job_id"], self.job.id)
        self.assertEqual(response.data["status"], "applied")
        self.assertTrue(JobApplication.objects.filter(
            external_user_id=self.user_id, job=self.job
        ).exists())

    def test_apply_duplicate_returns_409(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        self.client.post(url, {"user_id": self.user_id}, format="json")
        response = self.client.post(url, {"user_id": self.user_id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_apply_requires_user_id(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_apply_inactive_job_returns_400(self):
        self.job.is_active = False
        self.job.save(update_fields=["is_active"])
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(url, {"user_id": self.user_id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_my_applications(self):
        JobApplication.objects.create(
            external_user_id=self.user_id,
            job=self.job,
            applied_at="2026-05-17T12:00:00Z",
        )
        url = reverse("user_applications")
        response = self.client.get(url, {"external_user_id": self.user_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["job"]["title"], "Backend Engineer")

    def test_applicants_requires_employer_auth(self):
        url = reverse("job_applicants", kwargs={"job_id": self.job.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_applicants_with_employer_key(self):
        JobApplication.objects.create(
            external_user_id=self.other_user_id,
            job=self.job,
            applied_at="2026-05-17T12:00:00Z",
        )
        url = reverse("job_applicants", kwargs={"job_id": self.job.id})
        self.client.credentials(HTTP_X_EMPLOYER_KEY="test-employer-secret")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["user_id"], self.other_user_id)

    def test_applicants_scoped_staff_forbidden_for_non_staff(self):
        JobApplication.objects.create(
            external_user_id=self.other_user_id,
            job=self.job,
            applied_at="2026-05-17T12:00:00Z",
        )
        url = reverse("job_applicants", kwargs={"job_id": self.job.id})
        self.client.credentials(HTTP_X_EMPLOYER_KEY="test-employer-secret")
        response = self.client.get(
            url,
            {"external_user_id": self.other_user_id},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_applicants_scoped_staff_allowed(self):
        JobApplication.objects.create(
            external_user_id=self.other_user_id,
            job=self.job,
            applied_at="2026-05-17T12:00:00Z",
        )
        url = reverse("job_applicants", kwargs={"job_id": self.job.id})
        self.client.credentials(HTTP_X_EMPLOYER_KEY="test-employer-secret")
        response = self.client.get(
            url,
            {"external_user_id": self.user_id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
