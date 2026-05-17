"""Applicant identity from BFF request (and optional breneo-api enrichment)."""

from __future__ import annotations

from dataclasses import dataclass

from .breneo_user import external_user_field_from_request, external_user_id_from_request


@dataclass
class ApplicantProfile:
    user_id: str
    email: str = ""
    name: str = ""
    surname: str = ""

    def as_create_kwargs(self) -> dict[str, str]:
        return {
            "external_user_email": self.email,
            "external_user_name": self.name,
            "external_user_surname": self.surname,
        }


def _header(request, key: str) -> str:
    return (getattr(request, "headers", None) or {}).get(key, "").strip()


def applicant_profile_from_request(request) -> ApplicantProfile:
    """
    Read user id, email, name, surname from query/body/headers (BFF passes same as user id).
    """
    user_id = external_user_id_from_request(request) or _header(request, "X-Breneo-User-Id")
    email = external_user_field_from_request(
        request,
        "external_user_email",
        "user_email",
        "email",
    ) or _header(request, "X-Breneo-User-Email")
    name = external_user_field_from_request(
        request,
        "external_user_name",
        "user_name",
        "first_name",
        "firstName",
        "name",
    ) or _header(request, "X-Breneo-User-Name")
    surname = external_user_field_from_request(
        request,
        "external_user_surname",
        "user_surname",
        "last_name",
        "lastName",
        "surname",
    ) or _header(request, "X-Breneo-User-Surname")
    return ApplicantProfile(
        user_id=user_id,
        email=email,
        name=name,
        surname=surname,
    )


def _profile_from_breneo_dict(user_id: str, data: dict) -> ApplicantProfile:
    if not data:
        return ApplicantProfile(user_id=user_id)
    name = (
        (data.get("first_name") or data.get("name") or data.get("given_name") or "")
    ).strip()
    surname = (
        (data.get("last_name") or data.get("surname") or data.get("family_name") or "")
    ).strip()
    email = (data.get("email") or "").strip()
    return ApplicantProfile(user_id=user_id, email=email, name=name, surname=surname)


def enrich_applicant_profile(profile: ApplicantProfile) -> ApplicantProfile:
    """Fill missing email/name/surname from breneo-api when configured."""
    if not profile.user_id:
        return profile
    if profile.email and profile.name and profile.surname:
        return profile

    from .services.breneo_user_client import fetch_user_profiles

    profiles = fetch_user_profiles([profile.user_id])
    remote = _profile_from_breneo_dict(profile.user_id, profiles.get(profile.user_id) or {})
    return ApplicantProfile(
        user_id=profile.user_id,
        email=profile.email or remote.email,
        name=profile.name or remote.name,
        surname=profile.surname or remote.surname,
    )


def resolve_applicant_profile(request) -> ApplicantProfile:
    """Profile from request, enriched from breneo-api for any missing fields."""
    profile = applicant_profile_from_request(request)
    return enrich_applicant_profile(profile)
