import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.test import TestCase
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from .models import Company, CompanyStaffMembership


def _png_file(name: str = "logo.png"):
    buff = BytesIO()
    img = Image.new("RGB", (8, 8), color=(255, 0, 0))
    img.save(buff, format="PNG")
    buff.seek(0)
    buff.name = name
    return buff


class EmployerCompanyLogoAPITests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp_media_dir = tempfile.mkdtemp(prefix="test-employer-logo-")
        cls._original_storage = Company._meta.get_field("logo_upload").storage
        Company._meta.get_field("logo_upload").storage = FileSystemStorage(
            location=cls._tmp_media_dir
        )

    @classmethod
    def tearDownClass(cls):
        Company._meta.get_field("logo_upload").storage = cls._original_storage
        shutil.rmtree(cls._tmp_media_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="employer-api-user",
            password="test-pass-123",
        )
        self.client.credentials(HTTP_X_EMPLOYER_KEY="breneo2025")

        self.company = Company.objects.create(name="Logo API Co", employer_created=True)
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=str(self.user.id),
        )
        self.url = reverse("employer_company_detail", kwargs={"company_id": self.company.id})
        self.url_with_uid = f"{self.url}?external_user_id={self.user.id}"

    def test_successful_multipart_upload(self):
        with _png_file("upload.png") as fh:
            response = self.client.patch(
                self.url_with_uid,
                data={"logo_upload": fh},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.company.refresh_from_db()
        self.assertTrue(bool(self.company.logo_upload.name))
        self.assertIn("logo", response.data)
        self.assertIn("logo_upload", response.data)
        # With local FileSystemStorage, URLs are /media/...; API hides those from JSON by design.
        # Upload success is proven by the model field above; production Cloudinary URLs appear in logo/logo_upload.

    def test_update_without_image(self):
        response = self.client.patch(
            self.url_with_uid,
            data={"description": "Updated without touching logo"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.company.refresh_from_db()
        self.assertEqual(self.company.description, "Updated without touching logo")
        self.assertFalse(bool(self.company.logo_upload.name))

    def test_replace_existing_image(self):
        with _png_file("first.png") as fh1:
            first = self.client.patch(
                self.url_with_uid,
                data={"logo_upload": fh1},
                format="multipart",
            )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.company.refresh_from_db()
        first_name = self.company.logo_upload.name

        with _png_file("second.png") as fh2:
            second = self.client.patch(
                self.url_with_uid,
                data={"logo_upload": fh2},
                format="multipart",
            )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.company.refresh_from_db()
        second_name = self.company.logo_upload.name
        self.assertNotEqual(first_name, second_name)

    def test_delete_existing_image(self):
        with _png_file("to-delete.png") as fh:
            uploaded = self.client.patch(
                self.url_with_uid,
                data={"logo_upload": fh},
                format="multipart",
            )
        self.assertEqual(uploaded.status_code, status.HTTP_200_OK)

        deleted = self.client.delete(
            self.url_with_uid,
        )
        self.assertEqual(deleted.status_code, status.HTTP_200_OK)
        self.assertEqual(deleted.data["logo_upload"], None)
        self.company.refresh_from_db()
        self.assertFalse(bool(self.company.logo_upload))

    def test_logo_upload_alias_logo_upload_field_from_frontend(self):
        """Accept file under logoUpload (camelCase) and map to logo_upload."""
        with _png_file("camel.png") as fh:
            response = self.client.patch(
                self.url_with_uid,
                data={"logoUpload": fh},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.company.refresh_from_db()
        self.assertTrue(bool(self.company.logo_upload.name))

    def test_multipart_with_junk_logo_string_still_saves_file(self):
        """logo: \"null\" from JS must not block logo_upload."""
        with _png_file("with-null-logo.png") as fh:
            response = self.client.patch(
                self.url_with_uid,
                data={"logo": "null", "logo_upload": fh},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.company.refresh_from_db()
        self.assertTrue(bool(self.company.logo_upload.name))

    def test_unauthorized_returns_403(self):
        unauthorized = APIClient()
        response = unauthorized.patch(
            self.url_with_uid,
            data={"description": "No auth"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
