import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .authentication.application_auth import build_application_auth_headers
from .models import Company, CompanyStaffMembership, Job, JobApplication


def _django_auth_headers(user_id: str) -> dict[str, str]:
  h = build_application_auth_headers(user_id)
  return {
    "HTTP_X_BRENEO_USER_ID": h["X-Breneo-User-Id"],
    "HTTP_X_BRENEO_TIMESTAMP": h["X-Breneo-Timestamp"],
    "HTTP_X_BRENEO_SIGNATURE": h["X-Breneo-Signature"],
  }


@patch.dict(
  os.environ,
  {
    "APPLICATION_SIGNATURE_SECRET": "test-application-signature-secret",
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
    response = self.client.post(url, format="json", **_django_auth_headers(self.user_id))
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self._assert_success_envelope(response)
    self.assertEqual(response.data["data"]["user_id"], self.user_id)

  def test_apply_requires_signed_headers(self):
    url = reverse("job_apply", kwargs={"job_id": self.job.id})
    response = self.client.post(url, {}, format="json")
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    self._assert_success_envelope(response, success=False)

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
    response = self.client.post(url, format="json", **_django_auth_headers(self.user_id))
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertEqual(response.data.get("error"), "employer_job_only")

  def test_apply_duplicate_returns_409(self):
    url = reverse("job_apply", kwargs={"job_id": self.job.id})
    self.client.post(url, format="json", **_django_auth_headers(self.user_id))
    response = self.client.post(url, format="json", **_django_auth_headers(self.user_id))
    self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

  def test_list_my_applications_paginated(self):
    JobApplication.objects.create(
      external_user_id=self.user_id,
      job=self.job,
      applied_at=timezone.now(),
    )
    url = reverse("user_applications")
    response = self.client.get(url, **_django_auth_headers(self.user_id))
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(len(response.data["data"]["items"]), 1)

  def test_withdraw_application(self):
    JobApplication.objects.create(
      external_user_id=self.user_id,
      job=self.job,
      applied_at=timezone.now(),
    )
    url = reverse("job_withdraw_application", kwargs={"job_id": self.job.id})
    response = self.client.delete(url, **_django_auth_headers(self.user_id))
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    app = JobApplication.objects.get(external_user_id=self.user_id, job=self.job)
    self.assertIsNotNone(app.withdrawn_at)

  def test_job_serializer_supports_in_app_apply_flag(self):
    from .serializers import JobSerializer

    employer_data = JobSerializer(self.job).data
    self.assertTrue(employer_data["supports_in_app_apply"])

    fetched = Job.objects.create(
      title="Fetched",
      company=self.company,
      platform="lever",
      external_job_id="lv-1",
      apply_url="https://jobs.lever.co/x",
      is_active=True,
    )
    fetched_data = JobSerializer(fetched).data
    self.assertFalse(fetched_data["supports_in_app_apply"])

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


class ApplicationSignatureUnitTests(TestCase):
  @patch.dict(os.environ, {"APPLICATION_SIGNATURE_SECRET": "unit-test-secret"})
  def test_sign_and_verify(self):
    from .authentication.application_auth import (
      build_application_auth_headers,
      verify_application_signature,
    )

    headers = build_application_auth_headers("user-abc")
    self.assertTrue(
      verify_application_signature(
        headers["X-Breneo-User-Id"],
        headers["X-Breneo-Timestamp"],
        headers["X-Breneo-Signature"],
      )
    )
