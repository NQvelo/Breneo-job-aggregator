# jobs/fetchers/greenhouse.py
import httpx
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def clean_html(raw_html):
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(separator="\n").strip()

def fetch_full_description_from_url(url: str):
    """
    Fetch the HTML job page and extract description using common Greenhouse selectors.
    Only simple requests + BS4 (no JS).
    """
    try:
        r = httpx.get(url, timeout=8)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Common Greenhouse selectors:
        desc = soup.select_one("div.content") or soup.select_one(".posting-description") or soup.select_one("#content")
        if desc:
            return desc.get_text(separator="\n").strip()
        return ""
    except httpx.RequestError as e:
        logger.warning("Error fetching greenhouse job page %s: %s", url, e)
        return ""

def fetch_greenhouse(handle: str, company_name: str, logo: str | None = None):
    """
    Fetch postings via Greenhouse job board API endpoint.
    Normalizes jobs; attempts to fetch full description from absolute_url if content is empty.
    """
    jobs = []
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs"
    try:
        resp = httpx.get(api_url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("jobs", []):
            absolute = item.get("absolute_url")  # usually full job page URL
            content_html = item.get("content", "") or ""
            description = clean_html(content_html)
            if not description and absolute:
                # fallback to fetching page HTML (legal only if allowed by robots, caller should check)
                description = fetch_full_description_from_url(absolute)
            posting = {
                "company": company_name,
                "title": item.get("title", ""),
                "location": (item.get("location") or {}).get("name", ""),
                "team": (item.get("departments") or [""])[0] if item.get("departments") else "",
                "commitment": item.get("employment_type", ""),
                "apply_link": item.get("absolute_url"),
                "description": description,
                "posting_date": item.get("updated_at") or item.get("created_at") or "",
                "logo": logo,
                "source": "greenhouse",
                "raw": item,
            }
            jobs.append(posting)
    except httpx.RequestError as e:
        logger.warning("Greenhouse fetch error for %s (%s): %s", company_name, handle, e)
    return jobs
