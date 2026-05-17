import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Company, CompanyStaffMembership, Job, JobApplication


def _bff_headers(user_id: str, *, app_key: str = "test-application-api-secret") -> dict[str, str]:
    return {
        "HTTP_X_APPLICATION_KEY": app_key,
        "HTTP_CONTENT_TYPE": "application/json",
    }


@patch.dict(
    os.environ,
    {
        "APPLICATION_API_SECRET": "test-application-api-secret",
        "EMPLOYER_POST_SECRET": "test-employer-secret",
    },
)
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

    def _assert_success_envelope(self, response, *, success: bool = True):
        self.assertIn("success", response.data)
        self.assertEqual(response.data["success"], success)
        self.assertIn("message", response.data)
        self.assertIn("data", response.data)

    def test_apply_creates_application(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(
            url,
            {
                "external_user_id": self.user_id,
                "external_user_email": "jane@example.com",
                "external_user_name": "Jane",
                "external_user_surname": "Doe",
            },
            format="json",
            **_bff_headers(self.user_id),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self._assert_success_envelope(response)
        data = response.data["data"]
        self.assertEqual(data["user_id"], self.user_id)
        self.assertEqual(data["external_user_id"], self.user_id)
        self.assertEqual(data["user_email"], "jane@example.com")
        self.assertEqual(data["external_user_email"], "jane@example.com")
        self.assertEqual(data["user_name"], "Jane")
        self.assertEqual(data["external_user_name"], "Jane")
        self.assertEqual(data["user_surname"], "Doe")
        self.assertEqual(data["external_user_surname"], "Doe")
        row = JobApplication.objects.get(pk=data["id"])
        self.assertEqual(row.external_user_email, "jane@example.com")

    def test_apply_accepts_camelcase_bff_fields(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(
            url,
            {
                "external_user_id": self.user_id,
                "email": "camel@example.com",
                "firstName": "Camel",
                "lastName": "Case",
            },
            format="json",
            **_bff_headers(self.user_id),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertEqual(data["external_user_email"], "camel@example.com")
        self.assertEqual(data["external_user_name"], "Camel")
        self.assertEqual(data["external_user_surname"], "Case")

    def test_list_applications_includes_all_user_fields(self):
        JobApplication.objects.create(
            external_user_id=self.user_id,
            external_user_email="list@example.com",
            external_user_name="List",
            external_user_surname="User",
            job=self.job,
            applied_at=timezone.now(),
        )
        url = reverse("user_applications")
        response = self.client.get(
            url,
            {"external_user_id": self.user_id},
            **_bff_headers(self.user_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["data"]["items"][0]
        for key in (
            "external_user_id",
            "external_user_email",
            "external_user_name",
            "external_user_surname",
            "user_id",
            "user_email",
            "user_name",
            "user_surname",
        ):
            self.assertIn(key, item, msg=f"missing {key}")
        self.assertEqual(item["external_user_email"], "list@example.com")

    def test_apply_requires_bff_key(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(
            url,
            {"external_user_id": self.user_id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_apply_rejects_fetched_job(self):
        fetched = Job.objects.create(
            title="ATS Role",
            company=self.company,
            platform="greenhouse",
            external_job_id="gh-123",
            apply_url="https://boards.greenhouse.io/apply",
            is_active=True,
        )
        url = reverse("job_apply", kwargs={"job_id": fetched.id})
        response = self.client.post(
            url,
            {"external_user_id": self.user_id},
            format="json",
            **_bff_headers(self.user_id),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get("error"), "employer_job_only")

    def test_list_my_applications(self):
        JobApplication.objects.create(
            external_user_id=self.user_id,
            job=self.job,
            applied_at=timezone.now(),
        )
        url = reverse("user_applications")
        response = self.client.get(
            url,
            {"external_user_id": self.user_id},
            **_bff_headers(self.user_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["items"]), 1)

    def test_withdraw_application(self):
        JobApplication.objects.create(
            external_user_id=self.user_id,
            job=self.job,
            applied_at=timezone.now(),
        )
        url = reverse("job_withdraw_application", kwargs={"job_id": self.job.id})
        response = self.client.delete(
            url,
            {"external_user_id": self.user_id},
            **_bff_headers(self.user_id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        app = JobApplication.objects.get(external_user_id=self.user_id, job=self.job)
        self.assertIsNotNone(app.withdrawn_at)

    def test_applicants_with_employer_key(self):
        JobApplication.objects.create(
            external_user_id=self.other_user_id,
            job=self.job,
            applied_at=timezone.now(),
        )
        url = reverse("job_applicants", kwargs={"job_id": self.job.id})
        self.client.credentials(HTTP_X_EMPLOYER_KEY="test-employer-secret")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
