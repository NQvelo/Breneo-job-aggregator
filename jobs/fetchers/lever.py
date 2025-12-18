# jobs/fetchers/lever.py
import httpx
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def clean_html(raw_html):
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(separator="\n").strip()

def fetch_lever(handle: str, company_name: str, logo: str | None = None):
    """
    Fetch postings from Lever public API.
    Returns list of normalized job dicts.
    """
    jobs = []
    url = f"https://api.lever.co/v0/postings/{handle}?mode=json"
    try:
        resp = httpx.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        for item in data:
            # Some fields vary between companies; we normalize
            posting = {
                "company": company_name,
                "title": item.get("text") or item.get("title"),
                "location": item.get("categories", {}).get("location", ""),
                "team": item.get("categories", {}).get("team", ""),
                "commitment": item.get("categories", {}).get("commitment", ""),
                "apply_link": item.get("hostedUrl") or item.get("applyUrl"),
                "description": clean_html(item.get("description", "")),
                "posting_date": item.get("postDate") or item.get("datePosted") or "",
                "logo": logo,
                "source": "lever",
                "raw": item,  # optional: keep raw for debugging
            }
            jobs.append(posting)
    except httpx.RequestError as e:
        logger.warning("Lever fetch error for %s (%s): %s", company_name, handle, e)
    return jobs
