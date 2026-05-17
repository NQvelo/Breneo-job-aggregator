import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .authentication.breneo_auth import BreneoUser
from .models import Company, CompanyStaffMembership, Job, JobApplication


def auth_header(user_id: str) -> dict[str, str]:
    """DEBUG dev token: dev:<user_id>"""
    return {"HTTP_AUTHORIZATION": f"Bearer dev:{user_id}"}


@override_settings(DEBUG=True)
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

    def _assert_success_envelope(self, response, *, success: bool = True):
        self.assertIn("success", response.data)
        self.assertEqual(response.data["success"], success)
        self.assertIn("message", response.data)
        self.assertIn("data", response.data)

    def test_apply_creates_application(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(url, format="json", **auth_header(self.user_id))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self._assert_success_envelope(response)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["user_id"], self.user_id)
        self.assertEqual(response.data["data"]["job_id"], self.job.id)
        self.assertEqual(response.data["data"]["status"], "applied")

    def test_apply_requires_auth(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self._assert_success_envelope(response, success=False)

    def test_apply_duplicate_returns_409(self):
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        self.client.post(url, format="json", **auth_header(self.user_id))
        response = self.client.post(url, format="json", **auth_header(self.user_id))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self._assert_success_envelope(response, success=False)

    def test_apply_inactive_job_returns_400(self):
        self.job.is_active = False
        self.job.save(update_fields=["is_active"])
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(url, format="json", **auth_header(self.user_id))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_my_applications_paginated(self):
        JobApplication.objects.create(
            external_user_id=self.user_id,
            job=self.job,
            applied_at=timezone.now(),
        )
        url = reverse("user_applications")
        response = self.client.get(url, **auth_header(self.user_id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_success_envelope(response)
        self.assertEqual(len(response.data["data"]["items"]), 1)
        self.assertEqual(response.data["data"]["items"][0]["job"]["title"], "Backend Engineer")
        self.assertIn("pagination", response.data["data"])

    def test_withdraw_application(self):
        JobApplication.objects.create(
            external_user_id=self.user_id,
            job=self.job,
            applied_at=timezone.now(),
        )
        url = reverse("job_withdraw_application", kwargs={"job_id": self.job.id})
        response = self.client.delete(url, **auth_header(self.user_id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_success_envelope(response)
        app = JobApplication.objects.get(external_user_id=self.user_id, job=self.job)
        self.assertIsNotNone(app.withdrawn_at)

    def test_reapply_after_withdraw(self):
        app = JobApplication.objects.create(
            external_user_id=self.user_id,
            job=self.job,
            applied_at=timezone.now(),
            withdrawn_at=timezone.now(),
        )
        url = reverse("job_apply", kwargs={"job_id": self.job.id})
        response = self.client.post(url, format="json", **auth_header(self.user_id))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        app.refresh_from_db()
        self.assertIsNone(app.withdrawn_at)

    def test_applicants_requires_employer_auth(self):
        url = reverse("job_applicants", kwargs={"job_id": self.job.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
        self._assert_success_envelope(response)
        self.assertEqual(len(response.data["data"]["items"]), 1)
        self.assertEqual(response.data["data"]["items"][0]["user_id"], self.other_user_id)
        self.assertIn("user", response.data["data"]["items"][0])

    def test_applicants_scoped_staff_forbidden_for_non_staff(self):
        JobApplication.objects.create(
            external_user_id=self.other_user_id,
            job=self.job,
            applied_at=timezone.now(),
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
            applied_at=timezone.now(),
        )
        url = reverse("job_applicants", kwargs={"job_id": self.job.id})
        self.client.credentials(HTTP_X_EMPLOYER_KEY="test-employer-secret")
        response = self.client.get(
            url,
            {"external_user_id": self.user_id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(DEBUG=True)
class BreneoAuthUnitTests(TestCase):
    def test_resolve_dev_token(self):
        from .authentication.breneo_auth import resolve_breneo_user_from_token

        user = resolve_breneo_user_from_token("dev:test-uid")
        self.assertIsInstance(user, BreneoUser)
        self.assertEqual(user.id, "test-uid")
