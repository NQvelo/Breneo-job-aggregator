import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import Company, CompanyStaffMembership


@patch.dict(os.environ, {"EMPLOYER_POST_SECRET": "test-employer-secret"})
class CompanyStaffMembershipAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_EMPLOYER_KEY="test-employer-secret")
        self.company = Company.objects.create(name="Staff Co", employer_created=True)
        self.admin_id = "admin-user-1"
        self.member_id = "member-user-2"
        self.list_url = reverse("employer_staff_membership_list_create")

    def test_first_member_is_auto_admin_with_profile_fields(self):
        response = self.client.post(
            self.list_url,
            data={
                "company_id": self.company.id,
                "external_user_id": self.admin_id,
                "external_user_email": "admin@example.com",
                "external_user_name": "Ada",
                "external_user_surname": "Admin",
                "status": "member",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], CompanyStaffMembership.StaffStatus.ADMIN)
        self.assertEqual(response.data["external_user_email"], "admin@example.com")

        row = CompanyStaffMembership.objects.get(company=self.company, external_user_id=self.admin_id)
        self.assertEqual(row.status, CompanyStaffMembership.StaffStatus.ADMIN)

    def test_second_member_defaults_to_member_status(self):
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.admin_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        response = self.client.post(
            self.list_url,
            data={
                "company_id": self.company.id,
                "external_user_id": self.member_id,
                "external_user_email": "member@example.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], CompanyStaffMembership.StaffStatus.MEMBER)

    def test_can_create_pending_member(self):
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.admin_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        response = self.client.post(
            self.list_url,
            data={
                "company_id": self.company.id,
                "external_user_id": "pending-user",
                "status": "pending",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")

    def test_admin_can_remove_other_member_when_scoped(self):
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.admin_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        member_row = CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.member_id,
            status=CompanyStaffMembership.StaffStatus.MEMBER,
        )
        url = reverse(
            "employer_staff_membership_detail",
            kwargs={"membership_id": member_row.id},
        )
        response = self.client.delete(f"{url}?external_user_id={self.admin_id}")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CompanyStaffMembership.objects.filter(pk=member_row.id).exists())

    def test_non_admin_cannot_remove_member(self):
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.admin_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        member_row = CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.member_id,
            status=CompanyStaffMembership.StaffStatus.MEMBER,
        )
        other_id = "other-user-3"
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=other_id,
            status=CompanyStaffMembership.StaffStatus.MEMBER,
        )
        url = reverse(
            "employer_staff_membership_detail",
            kwargs={"membership_id": member_row.id},
        )
        response = self.client.delete(f"{url}?external_user_id={other_id}")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(CompanyStaffMembership.objects.filter(pk=member_row.id).exists())

    def test_admin_cannot_remove_self(self):
        admin_row = CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.admin_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        url = reverse(
            "employer_staff_membership_detail",
            kwargs={"membership_id": admin_row.id},
        )
        response = self.client.delete(f"{url}?external_user_id={self.admin_id}")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_remove_only_admin(self):
        admin_row = CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.admin_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        url = reverse(
            "employer_staff_membership_detail",
            kwargs={"membership_id": admin_row.id},
        )
        response = self.client.delete(f"{url}?external_user_id=server-only")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_admin_can_promote_member(self):
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.admin_id,
            status=CompanyStaffMembership.StaffStatus.ADMIN,
        )
        member_row = CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=self.member_id,
            status=CompanyStaffMembership.StaffStatus.MEMBER,
        )
        url = reverse(
            "employer_staff_membership_detail",
            kwargs={"membership_id": member_row.id},
        )
        denied = self.client.patch(
            f"{url}?external_user_id={self.member_id}",
            data={"status": "admin"},
            format="json",
        )
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)

        allowed = self.client.patch(
            f"{url}?external_user_id={self.admin_id}",
            data={"status": "admin"},
            format="json",
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        member_row.refresh_from_db()
        self.assertEqual(member_row.status, CompanyStaffMembership.StaffStatus.ADMIN)

    def test_pending_member_no_scoped_company_access(self):
        pending_id = "pending-user-99"
        CompanyStaffMembership.objects.create(
            company=self.company,
            external_user_id=pending_id,
            status=CompanyStaffMembership.StaffStatus.PENDING,
        )
        url = reverse("employer_company_detail", kwargs={"company_id": self.company.id})
        response = self.client.get(f"{url}?external_user_id={pending_id}")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
