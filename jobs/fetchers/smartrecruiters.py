# jobs/fetchers/smartrecruiters.py
import httpx
import logging

logger = logging.getLogger(__name__)


def fetch_smartrecruiters(company_handle: str, company_name: str, logo: str | None = None):
    """
    SmartRecruiters has JSON endpoints for some customers, but not a single public API for all.
    This function attempts to fetch common JSON listing patterns, but success depends on company.
    For many companies you'll need to find their specific API/endpoint.
    """
    jobs = []
    # Try common SmartRecruiters API pattern (some companies expose /open-api)
    urls_to_try = [
        f"https://api.smartrecruiters.com/v1/companies/{company_handle}/jobs",
        f"https://api.smartrecruiters.com/v1/companies/{company_handle}/postings",
    ]
    for url in urls_to_try:
        try:
            r = httpx.get(url, timeout=8)
            if r.status_code != 200:
                continue
            data = r.json()
            # Data format varies: try to normalize
            items = data.get("content") or data.get("jobs") or data.get("data") or []
            for item in items:
                jobs.append({
                    "company": company_name,
                    "title": item.get("name") or item.get("title") or item.get("jobTitle"),
                    "location": item.get("location") or item.get("city") or "",
                    "team": item.get("department") or "",
                    "commitment": item.get("employmentType") or "",
                    "apply_link": item.get("applyUrl") or item.get("link") or "",
                    "description": item.get("description") or "",
                    "posting_date": item.get("createdDate") or item.get("postedAt") or "",
                    "logo": logo,
                    "source": "smartrecruiters",
                    "raw": item,
                })
            if jobs:
                break
        except httpx.RequestError as e:
            logger.warning("SmartRecruiters fetch error for %s (%s): %s", company_name, company_handle, e)
    return jobs
