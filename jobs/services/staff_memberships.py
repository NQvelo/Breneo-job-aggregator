"""Company staff membership helpers (profile snapshot, admin rules, safe removal)."""

from __future__ import annotations

from django.db import transaction

from ..applicant_profile import ApplicantProfile, applicant_profile_from_request, enrich_applicant_profile
from ..models import Company, CompanyStaffMembership


def resolve_staff_profile(request, external_user_id: str) -> ApplicantProfile:
    """
    Profile for a staff row: request fields/headers, keyed to the membership user id,
    with optional breneo-api enrichment (same as job applications).
    """
    profile = applicant_profile_from_request(request)
    if not external_user_id:
        return profile
    if profile.user_id and profile.user_id != external_user_id:
        profile = ApplicantProfile(
            user_id=external_user_id,
            email=profile.email,
            name=profile.name,
            surname=profile.surname,
        )
    elif not profile.user_id:
        profile = ApplicantProfile(user_id=external_user_id)
    return enrich_applicant_profile(profile)


def staff_profile_create_kwargs(request, external_user_id: str) -> dict[str, str]:
    return resolve_staff_profile(request, external_user_id).as_create_kwargs()


def merge_staff_profile_kwargs(
    existing: CompanyStaffMembership,
    kwargs: dict[str, str],
) -> dict[str, str]:
    """Keep stored values when incoming profile fields are empty."""
    return {
        "external_user_email": kwargs.get("external_user_email") or existing.external_user_email,
        "external_user_name": kwargs.get("external_user_name") or existing.external_user_name,
        "external_user_surname": kwargs.get("external_user_surname") or existing.external_user_surname,
    }


def is_first_staff_for_company(company: Company) -> bool:
    return not CompanyStaffMembership.objects.filter(company=company).exists()


def resolve_is_admin_on_create(
    company: Company,
    requested: bool | None,
) -> bool:
    """First member for a company is always admin."""
    if is_first_staff_for_company(company):
        return True
    return bool(requested)


def requester_membership(
    company: Company,
    requester_user_id: str,
) -> CompanyStaffMembership | None:
    if not requester_user_id:
        return None
    return CompanyStaffMembership.objects.filter(
        company=company,
        external_user_id=requester_user_id,
    ).first()


def admin_count_for_company(company: Company) -> int:
    return CompanyStaffMembership.objects.filter(company=company, is_admin=True).count()


def check_can_change_admin_flag(
    *,
    company: Company,
    requester_user_id: str,
    instance: CompanyStaffMembership,
    new_is_admin: bool,
) -> str | None:
    """
    When external_user_id is provided on the request, only admins may change is_admin.
    Cannot demote the last admin.
    """
    if not requester_user_id:
        return None

    requester = requester_membership(company, requester_user_id)
    if requester is None or not requester.is_admin:
        return "Only company admins can change admin status."

    if instance.is_admin and not new_is_admin and admin_count_for_company(company) <= 1:
        return "Cannot remove admin from the only admin for this company."

    return None


def check_can_remove_staff_member(
    *,
    company: Company,
    requester_user_id: str,
    target: CompanyStaffMembership,
) -> str | None:
    """
  When external_user_id is provided, only a company admin may remove another member
  of the same company. Cannot remove yourself or the last admin.
    """
    if not requester_user_id:
        return None

    requester = requester_membership(company, requester_user_id)
    if requester is None or not requester.is_admin:
        return "Only company admins can remove staff members."

    if target.pk == requester.pk:
        return "Admins cannot remove themselves. Transfer admin to another member first."

    if target.is_admin and admin_count_for_company(company) <= 1:
        return "Cannot remove the only admin for this company."

    return None


@transaction.atomic
def delete_staff_membership(
    membership: CompanyStaffMembership,
    *,
    requester_user_id: str = "",
) -> tuple[bool, str]:
    company = Company.objects.select_for_update().get(pk=membership.company_id)
    target = CompanyStaffMembership.objects.select_for_update().get(pk=membership.pk)
    err = check_can_remove_staff_member(
        company=company,
        requester_user_id=requester_user_id,
        target=target,
    )
    if err:
        return False, err
    target.delete()
    return True, ""
