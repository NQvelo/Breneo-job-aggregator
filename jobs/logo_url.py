"""Resolve the logo URL shown in APIs (uploaded file > URL field > generated fallback)."""

from __future__ import annotations


def resolved_company_logo_url(company, request=None) -> str:
    """
    Prefer employer-uploaded image, then stored logo URL.

    For imported/scraped companies only, fall back to Logo.dev-style URL from name.
    Employer-portal companies (employer_created) never use that API — they must set
    logo_upload or logo manually; otherwise the resolved logo is empty.
    """
    from jobs.fetchers import get_logo_url

    def _public_url_or_empty(url: str | None) -> str:
        if not url:
            return ""
        if url.startswith(("http://", "https://")):
            return url
        if request is not None and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url

    if getattr(company, "logo_upload", None) and company.logo_upload:
        return _public_url_or_empty(company.logo_upload.url)
    if company.logo:
        return _public_url_or_empty(company.logo)
    if getattr(company, "employer_created", False):
        return ""
    return get_logo_url(company.name)
