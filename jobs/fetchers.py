import httpx
from bs4 import BeautifulSoup
from .utils import parse_date, robots_allowed
import logging
from urllib.parse import urljoin
import feedparser
from django.utils import timezone
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

HEADERS = {"User-Agent": "BreneoJobAggregator/1.0 (+https://yourdomain.example)"}
LOGO_DEV_PUBLIC_KEY = "pk_K96TtQYUTvy3hHXDyIEUqw"
BASE_URL = "https://jobs.ge"


def safe_get(url, timeout=8):
    r = httpx.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def get_logo_url(company_name: str, size=101) -> str:
    safe_name = company_name.replace(" ", "")
    return f"https://img.logo.dev/name/{safe_name}?token={LOGO_DEV_PUBLIC_KEY}&size={size}&retina=true"


def clean_html_to_text(html_content):
    """
    Convert HTML content to clean plain text.
    Removes all HTML tags and normalizes whitespace.
    
    Args:
        html_content: HTML string or None
        
    Returns:
        Clean plain text string
    """
    if not html_content:
        return ""
    
    try:
        # Parse HTML and extract text
        soup = BeautifulSoup(str(html_content), "html.parser")
        text = soup.get_text(separator="\n")
        
        # Normalize whitespace: replace multiple newlines with double newline, 
        # replace multiple spaces with single space, strip each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(line for line in lines if line)
        
        # Replace multiple consecutive newlines with double newline
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Final strip
        return text.strip()
    except Exception as e:
        logger.warning(f"Error cleaning HTML: {e}")
        # Fallback: try to remove HTML tags with regex if BeautifulSoup fails
        text = re.sub(r'<[^>]+>', '', str(html_content))
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


def fetch_greenhouse(handle, company_name, logo=None):
    logo = logo or get_logo_url(company_name)
    url = f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs"
    jobs = []
    try:
        r = safe_get(url)
        data = r.json()
        for job in data.get("jobs", []):
            job_id = job.get("id")
            absolute_url = job.get("absolute_url") or f"https://boards.greenhouse.io/{handle}/jobs/{job_id}"
            content = job.get("content", "")
            
            # If the API doesn't include content in the list endpoint, fetch individual job details
            if not content and job_id:
                try:
                    job_url = f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs/{job_id}"
                    job_r = safe_get(job_url)
                    job_data = job_r.json()
                    content = job_data.get("content", "")
                    # Update job data with individual job details if needed
                    if job_data.get("first_published") and not job.get("first_published"):
                        job["first_published"] = job_data.get("first_published")
                except Exception as e:
                    logger.warning("Failed to fetch individual job details for %s job %s: %s", company_name, job_id, e)
                    content = ""

            text_desc = clean_html_to_text(content)
            # Prefer first_published for accurate posting date
            posted_at = parse_date(
                job.get("first_published") or 
                job.get("updated_at") or 
                job.get("created_at")
            ) or timezone.now()  # Fallback to current time if no date found
            
            jobs.append({
                "title": job.get("title") or "",
                "company": company_name,
                "location": (job.get("location") or {}).get("name", ""),
                "description": text_desc,
                "apply_url": absolute_url,
                "posted_at": posted_at,
                "platform": "greenhouse",
                "external_job_id": str(job_id),
                "raw": job,
                "logo": logo,
            })
    except Exception:
        logger.exception("Greenhouse fetch error for %s (%s)", company_name, handle)
    return jobs


def fetch_lever(handle, company_name, logo=None):
    logo = logo or get_logo_url(company_name)
    url = f"https://api.lever.co/v0/postings/{handle}?mode=json"
    jobs = []
    try:
        r = safe_get(url)
        data = r.json()
        for job in data:
            job_id = job.get("id") or job.get("uuid") or job.get("postingId")
            hosted_url = job.get("hostedUrl") or job.get("applyUrl") or job.get("url")
            html_desc = job.get("description") or ""
            text_desc = clean_html_to_text(html_desc)
            jobs.append({
                "title": job.get("text") or job.get("title") or "",
                "company": company_name,
                "location": (job.get("categories") or {}).get("location", ""),
                "description": text_desc,
                "apply_url": hosted_url,
                "posted_at": parse_date(job.get("postDate") or job.get("datePosted")),
                "platform": "lever",
                "external_job_id": str(job_id),
                "raw": job,
                "logo": logo,
            })
    except Exception:
        logger.exception("Lever fetch error for %s (%s)", company_name, handle)
    return jobs


def fetch_workable(company_slug, company_name, logo=None):
    logo = logo or get_logo_url(company_name)
    jobs = []
    try:
        rss_url = f"https://{company_slug}.workable.com/jobs.rss"
        r = safe_get(rss_url)
        soup = BeautifulSoup(r.content, "xml")
        for item in soup.find_all("item"):
            link = item.link.text if item.link else None
            desc = (item.description.text if item.description else "")
            jobs.append({
                "title": item.title.text if item.title else "",
                "company": company_name,
                "location": None,
                "description": clean_html_to_text(desc),
                "apply_url": link,
                "posted_at": None,
                "platform": "workable",
                "external_job_id": link,
                "raw": {},
                "logo": logo,
            })
    except Exception:
        logger.info("Workable RSS not available for %s", company_name)
    return jobs


def fetch_rss(feed_url, company_name, logo=None):
    import feedparser
    logo = logo or get_logo_url(company_name)
    jobs = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            link = entry.get("link")
            desc = entry.get("summary") or entry.get("description") or ""
            jobs.append({
                "title": entry.get("title") or "",
                "company": company_name,
                "location": None,
                "description": clean_html_to_text(desc),
                "apply_url": link,
                "posted_at": parse_date(entry.get("published") or entry.get("updated")),
                "platform": "rss",
                "external_job_id": link,
                "raw": entry,
                "logo": logo,
            })
    except Exception:
        logger.exception("RSS fetch error for %s: %s", company_name, feed_url)
    return jobs


def fetch_generic_career_page(list_url, company_name, logo=None, selector=None):
    logo = logo or get_logo_url(company_name)
    jobs = []
    try:
        if not robots_allowed(list_url):
            logger.warning("Scraping disallowed by robots.txt: %s", list_url)
            return jobs
        r = safe_get(list_url)
        soup = BeautifulSoup(r.content, "html.parser")
        sel = selector or "a[href*='/jobs/'], a[href*='/careers/'], a[href*='careers']"
        for a in soup.select(sel):
            title = a.get_text(strip=True)
            href = a.get("href")
            if not href:
                continue
            full_url = href if href.startswith("http") else urljoin(list_url, href)
            jobs.append({
                "title": title or full_url,
                "company": company_name,
                "location": None,
                "description": None,
                "apply_url": full_url,
                "posted_at": None,
                "platform": "career_page",
                "external_job_id": full_url,
                "raw": {},
                "logo": logo,
            })
    except Exception:
        logger.exception("Generic career page fetch failed for %s", list_url)
    return jobs


def fetch_jobs_ge_listings(list_url, company_name="Local Georgian", logo=None, limit=20):
    logo = logo or get_logo_url(company_name)
    jobs = []
    try:
        if not robots_allowed(list_url):
            logger.warning("Scraping disallowed by robots.txt: %s", list_url)
            return jobs
        r = safe_get(list_url)
        soup = BeautifulSoup(r.content, "html.parser")
        job_cards = soup.select(".job-item")[:limit]
        for card in job_cards:
            title_el = card.select_one(".job-title a")
            company_el = card.select_one(".company-name")
            if not title_el:
                continue
            href = title_el.get("href")
            full_url = href if href.startswith("http") else urljoin(BASE_URL, href)
            jobs.append({
                "title": title_el.text.strip(),
                "company": company_el.text.strip() if company_el else company_name,
                "location": "Georgia",
                "description": None,
                "apply_url": full_url,
                "posted_at": None,
                "platform": "jobs.ge",
                "external_job_id": full_url,
                "raw": {},
                "logo": logo,
            })
    except Exception:
        logger.exception("jobs.ge fetch failed for %s", list_url)
    return jobs


def fetch_ashby(handle: str, company_name: str, logo=None):
    """
    Fetch jobs from AshbyHQ
    Example: https://jobs.ashbyhq.com/notion
    """
    import httpx
    logo = logo or get_logo_url(company_name)

    url = f"https://jobs.ashbyhq.com/api/non-user-graphql"
    payload = {
        "operationName": "JobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": handle},
        "query": """
        query JobBoardWithTeams($organizationHostedJobsPageName: String!) {
          jobBoardWithTeams(
            organizationHostedJobsPageName: $organizationHostedJobsPageName
          ) {
            jobPostings {
              id
              title
              locationName
              postedAt
              externalLink
              descriptionHtml
            }
          }
        }
        """
    }

    jobs = []
    try:
        r = httpx.post(url, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()

        postings = data["data"]["jobBoardWithTeams"]["jobPostings"]
        for j in postings:
            html_desc = j.get("descriptionHtml") or ""
            text_desc = clean_html_to_text(html_desc)
            jobs.append({
                "title": j["title"],
                "company": company_name,
                "location": j.get("locationName"),
                "description": text_desc,
                "apply_url": j.get("externalLink"),
                "external_job_id": j["id"],
                "posted_at": j.get("postedAt"),
                "raw": j,
                "logo": logo,
            })

    except Exception:
        logger.exception("Ashby fetch failed for %s", company_name)

    return jobs


def fetch_linkedin(jobs_api_url, company_name, api_key=None, logo=None):
    """
    LinkedIn does not provide a public API for job listings. This stub supports an
    optional external jobs API (e.g. SerpAPI, Apify, or a custom proxy).
    Set LINKEDIN_JOBS_API_URL (and optionally LINKEDIN_JOBS_API_KEY) in settings/env,
    and add a company with platform="linkedin" and url=<that API URL>.
    Returns [] if no URL configured or request fails.
    """
    logo = logo or get_logo_url(company_name)
    if not jobs_api_url:
        logger.debug("LinkedIn: no jobs API URL configured")
        return []
    try:
        headers = {**HEADERS}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        r = httpx.get(jobs_api_url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        jobs = []
        raw_list = data.get("jobs", data.get("results", data)) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for job in raw_list if isinstance(raw_list, list) else []:
            jobs.append({
                "title": job.get("title") or job.get("name") or "",
                "company": company_name,
                "location": job.get("location") or job.get("locationName"),
                "description": clean_html_to_text(job.get("description") or job.get("descriptionHtml") or ""),
                "apply_url": job.get("url") or job.get("applyUrl") or job.get("link") or "",
                "posted_at": parse_date(job.get("postedAt") or job.get("publishedAt") or job.get("date")),
                "platform": "linkedin",
                "external_job_id": str(job.get("id") or job.get("jobId") or job.get("url", "")),
                "raw": job,
                "logo": logo,
            })
        return jobs
    except Exception:
        logger.exception("LinkedIn jobs API fetch failed for %s", company_name)
        return []


def _smartrecruiters_flatten_sections(sections: dict | list | None) -> str:
    """Merge SmartRecruiters jobAd.sections HTML into one string."""
    if not sections:
        return ""
    chunks: list[str] = []
    if isinstance(sections, dict):
        for sec in sections.values():
            if isinstance(sec, dict) and sec.get("text"):
                chunks.append(str(sec["text"]))
    elif isinstance(sections, list):
        for sec in sections:
            if isinstance(sec, dict) and sec.get("text"):
                chunks.append(str(sec["text"]))
    return "\n\n".join(chunks)


def fetch_smartrecruiters(
    company_handle: str,
    company_name: str,
    logo: str | None = None,
    *,
    remote_only: bool = True,
    fetch_details: bool = True,
) -> list:
    """
    SmartRecruiters public Posting API (no auth for public listings).
    https://developers.smartrecruiters.com/reference/v1listpostings

    company_handle: identifier in https://jobs.smartrecruiters.com/{handle}/...
    remote_only: request locationType=REMOTE (still may include US-only remote roles).
    fetch_details: one GET per posting for applyUrl + full description (recommended).
    """
    logo = logo or get_logo_url(company_name)
    base = "https://api.smartrecruiters.com/v1/companies"
    jobs: list = []
    offset = 0
    limit = 100
    try:
        while True:
            params: dict = {"limit": limit, "offset": offset, "destination": "PUBLIC"}
            if remote_only:
                params["locationType"] = "REMOTE"
            url = f"{base}/{company_handle}/postings"
            r = httpx.get(url, headers=HEADERS, params=params, timeout=30)
            if r.status_code == 404:
                logger.warning(
                    "SmartRecruiters: no postings for identifier %r (404)", company_handle
                )
                break
            r.raise_for_status()
            data = r.json()
            content = data.get("content") or []
            if not content:
                break
            for item in content:
                pid = item.get("id")
                if not pid:
                    continue
                cid = (item.get("company") or {}).get("identifier") or company_handle
                loc = item.get("location") or {}
                loc_str = loc.get("fullLocation") or ""
                if not loc_str.strip():
                    loc_str = ", ".join(
                        filter(
                            None,
                            [loc.get("city"), loc.get("region"), loc.get("country")],
                        )
                    )
                if loc.get("remote"):
                    loc_str = f"Remote · {loc_str}" if loc_str else "Remote"

                apply_url = ""
                description_html = ""
                if fetch_details:
                    try:
                        dr = httpx.get(f"{base}/{cid}/postings/{pid}", headers=HEADERS, timeout=25)
                        if dr.status_code == 200:
                            det = dr.json()
                            apply_url = (det.get("applyUrl") or det.get("postingUrl") or "").strip()
                            ja = det.get("jobAd") or {}
                            sections = ja.get("sections")
                            description_html = _smartrecruiters_flatten_sections(sections)
                    except Exception as e:
                        logger.debug("SmartRecruiters detail %s/%s: %s", cid, pid, e)

                if not apply_url:
                    apply_url = (item.get("ref") or "").strip()

                ext = item.get("uuid") or str(pid)
                jobs.append(
                    {
                        "title": item.get("name") or "",
                        "company": company_name,
                        "location": loc_str or "Remote",
                        "description": clean_html_to_text(description_html)
                        if description_html
                        else "",
                        "apply_url": apply_url,
                        "posted_at": parse_date(item.get("releasedDate")),
                        "platform": "smartrecruiters",
                        "external_job_id": str(ext),
                        "raw": {**item, "source": "smartrecruiters"},
                        "logo": logo,
                    }
                )
            offset += len(content)
            total_found = int(data.get("totalFound") or 0)
            if offset >= total_found or len(content) < limit:
                break
    except Exception:
        logger.exception("SmartRecruiters fetch error for %s (%s)", company_name, company_handle)
    return jobs


def fetch_remotive(api_url: str | None, aggregate_name: str, logo: str | None = None) -> list:
    """
    Remotive public API — remote jobs only.
    Terms: https://remotive.com/api-documentation (link to their job URLs; avoid excessive polling).
    """
    logo = logo or get_logo_url("Remotive")
    url = (api_url or "").strip() or "https://remotive.com/api/remote-jobs"
    jobs: list = []
    try:
        r = httpx.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        for job in data.get("jobs") or []:
            jid = job.get("id")
            if jid is None:
                continue
            co = (job.get("company_name") or "").strip() or aggregate_name
            loc = (job.get("candidate_required_location") or "").strip() or "Remote"
            jobs.append(
                {
                    "title": job.get("title") or "",
                    "company": co,
                    "location": loc,
                    "description": clean_html_to_text(job.get("description") or ""),
                    "apply_url": (job.get("url") or "").strip(),
                    "posted_at": parse_date(job.get("publication_date")),
                    "platform": "remotive",
                    "external_job_id": str(jid),
                    "raw": {
                        **job,
                        "source": "Remotive",
                        "remotive_terms": "https://remotive.com/api-documentation",
                    },
                    "logo": job.get("company_logo") or logo,
                }
            )
    except Exception:
        logger.exception("Remotive fetch failed for %s", url)
    return jobs


def fetch_adzuna(company_name: str, what: str = "remote", logo: str | None = None) -> list:
    """
    Adzuna aggregated search (remote-oriented query). Requires ADZUNA_APP_ID / ADZUNA_APP_KEY.
    https://developer.adzuna.com/docs/search
    """
    from django.conf import settings

    app_id = getattr(settings, "ADZUNA_APP_ID", "") or ""
    app_key = getattr(settings, "ADZUNA_APP_KEY", "") or ""
    country = getattr(settings, "ADZUNA_COUNTRY", None) or "gb"
    if not app_id or not app_key:
        logger.info("Adzuna: skip (set ADZUNA_APP_ID and ADZUNA_APP_KEY)")
        return []

    logo = logo or get_logo_url(company_name or "Adzuna")
    jobs: list = []
    page = 1
    max_pages = 3
    try:
        while page <= max_pages:
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
            r = httpx.get(
                url,
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": what,
                    "results_per_page": 50,
                },
                headers=HEADERS,
                timeout=25,
            )
            r.raise_for_status()
            data = r.json()
            results = data.get("results") or []
            for res in results:
                co = (res.get("company") or {}).get("display_name") or "Unknown"
                loc = (res.get("location") or {}).get("display_name") or ""
                jobs.append(
                    {
                        "title": res.get("title") or "",
                        "company": co.strip() or "Unknown",
                        "location": loc or "Remote",
                        "description": clean_html_to_text(res.get("description") or ""),
                        "apply_url": (res.get("redirect_url") or res.get("url") or "").strip(),
                        "posted_at": parse_date(res.get("created")),
                        "platform": "adzuna",
                        "external_job_id": str(res.get("id")),
                        "raw": {**res, "source": "adzuna"},
                        "logo": logo,
                    }
                )
            if len(results) < 50:
                break
            page += 1
    except Exception:
        logger.exception("Adzuna fetch failed")
    return jobs


# import httpx
# from bs4 import BeautifulSoup
# from .utils import parse_date, robots_allowed
# import logging
# from urllib.parse import urljoin

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)


# HEADERS = {"User-Agent": "BreneoJobAggregator/1.0 (+https://yourdomain.example)"}


# def safe_get(url, timeout=8):
#     r = httpx.get(url, headers=HEADERS, timeout=timeout)
#     r.raise_for_status()
#     return r


# def fetch_greenhouse(handle, company_name, logo=None):
#     url = f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs"
#     jobs = []
#     try:
#         r = safe_get(url)
#         data = r.json()
#         for job in data.get("jobs", []):
#             job_id = job.get("id")
#             absolute_url = job.get("absolute_url") or f"https://boards.greenhouse.io/{handle}/jobs/{job_id}"
#             content = job.get("content", "")
#             text_desc = BeautifulSoup(content or "", "html.parser").get_text(separator="\n").strip()
#             jobs.append({
#                 "title": job.get("title") or "",
#                 "company": company_name,
#                 "location": (job.get("location") or {}).get("name", ""),
#                 "description": text_desc,
#                 "apply_url": absolute_url,
#                 "posted_at": parse_date(job.get("updated_at") or job.get("created_at")),
#                 "platform": "greenhouse",
#                 "external_job_id": str(job_id),
#                 "raw": job,
#                 "logo": logo,
#             })
#     except Exception:
#         logger.exception("Greenhouse fetch error for %s (%s)", company_name, handle)
#     return jobs


# def fetch_lever(handle, company_name, logo=None):
#     url = f"https://api.lever.co/v0/postings/{handle}?mode=json"
#     jobs = []
#     try:
#         r = safe_get(url)
#         data = r.json()
#         for job in data:
#             job_id = job.get("id") or job.get("uuid") or job.get("postingId")
#             hosted_url = job.get("hostedUrl") or job.get("applyUrl") or job.get("url")
#             html_desc = job.get("description") or ""
#             text_desc = BeautifulSoup(html_desc, "html.parser").get_text(separator="\n").strip()
#             jobs.append({
#                 "title": job.get("text") or job.get("title") or "",
#                 "company": company_name,
#                 "location": (job.get("categories") or {}).get("location", ""),
#                 "description": text_desc,
#                 "apply_url": hosted_url,
#                 "posted_at": parse_date(job.get("postDate") or job.get("datePosted")),
#                 "platform": "lever",
#                 "external_job_id": str(job_id),
#                 "raw": job,
#                 "logo": logo,
#             })
#     except Exception:
#         logger.exception("Lever fetch error for %s (%s)", company_name, handle)
#     return jobs


# def fetch_workable(company_slug, company_name, logo=None):
#     jobs = []
#     try:
#         rss_url = f"https://{company_slug}.workable.com/jobs.rss"
#         r = safe_get(rss_url)
#         soup = BeautifulSoup(r.content, "xml")
#         for item in soup.find_all("item"):
#             link = item.link.text if item.link else None
#             desc = (item.description.text if item.description else "")
#             jobs.append({
#                 "title": item.title.text if item.title else "",
#                 "company": company_name,
#                 "location": None,
#                 "description": BeautifulSoup(desc, "html.parser").get_text(),
#                 "apply_url": link,
#                 "posted_at": None,
#                 "platform": "workable",
#                 "external_job_id": link,
#                 "raw": {},
#                 "logo": logo,
#             })
#     except Exception:
#         logger.info("Workable RSS not available for %s", company_name)
#     return jobs


# def fetch_rss(feed_url, company_name, logo=None):
#     import feedparser
#     jobs = []
#     try:
#         feed = feedparser.parse(feed_url)
#         for entry in feed.entries:
#             link = entry.get("link")
#             desc = entry.get("summary") or entry.get("description") or ""
#             jobs.append({
#                 "title": entry.get("title") or "",
#                 "company": company_name,
#                 "location": None,
#                 "description": BeautifulSoup(desc, "html.parser").get_text(),
#                 "apply_url": link,
#                 "posted_at": parse_date(entry.get("published") or entry.get("updated")),
#                 "platform": "rss",
#                 "external_job_id": link,
#                 "raw": entry,
#                 "logo": logo,
#             })
#     except Exception:
#         logger.exception("RSS fetch error for %s: %s", company_name, feed_url)
#     return jobs


# BASE_URL = "https://jobs.ge"


# def fetch_jobs_ge_listings(list_url, company_name="Local Georgian", logo=None, limit=20):
#     jobs = []
#     try:
#         if not robots_allowed(list_url):
#             logger.warning("Scraping disallowed by robots.txt: %s", list_url)
#             return jobs
#         r = safe_get(list_url)
#         soup = BeautifulSoup(r.content, "html.parser")
#         job_cards = soup.select(".job-item")[:limit]
#         for card in job_cards:
#             title_el = card.select_one(".job-title a")
#             company_el = card.select_one(".company-name")
#             if not title_el:
#                 continue
#             href = title_el.get("href")
#             full_url = href if href.startswith("http") else urljoin(BASE_URL, href)
#             jobs.append({
#                 "title": title_el.text.strip(),
#                 "company": company_el.text.strip() if company_el else company_name,
#                 "location": "Georgia",
#                 "description": None,
#                 "apply_url": full_url,
#                 "posted_at": None,
#                 "platform": "jobs.ge",
#                 "external_job_id": full_url,
#                 "raw": {},
#                 "logo": logo,
#             })
#     except Exception:
#         logger.exception("jobs.ge fetch failed for %s", list_url)
#     return jobs


# def fetch_generic_career_page(list_url, company_name, logo=None, selector=None):
#     jobs = []
#     try:
#         if not robots_allowed(list_url):
#             logger.warning("Scraping disallowed by robots.txt: %s", list_url)
#             return jobs
#         r = safe_get(list_url)
#         soup = BeautifulSoup(r.content, "html.parser")
#         sel = selector or "a[href*='/jobs/'], a[href*='/careers/'], a[href*='careers']"
#         for a in soup.select(sel):
#             title = a.get_text(strip=True)
#             href = a.get("href")
#             if not href:
#                 continue
#             full_url = href if href.startswith("http") else urljoin(list_url, href)
#             jobs.append({
#                 "title": title or full_url,
#                 "company": company_name,
#                 "location": None,
#                 "description": None,
#                 "apply_url": full_url,
#                 "posted_at": None,
#                 "platform": "career_page",
#                 "external_job_id": full_url,
#                 "raw": {},
#                 "logo": logo,
#             })
#     except Exception:
#         logger.exception("Generic career page fetch failed for %s", list_url)
#     return jobs


# def fetch_ashby(handle: str, company_name: str, logo: str = ""):
#     """
#     Fetch jobs from AshbyHQ
#     Example: https://jobs.ashbyhq.com/notion
#     """
#     import httpx

#     url = f"https://jobs.ashbyhq.com/api/non-user-graphql"
#     payload = {
#         "operationName": "JobBoardWithTeams",
#         "variables": {
#             "organizationHostedJobsPageName": handle
#         },
#         "query": """
#         query JobBoardWithTeams($organizationHostedJobsPageName: String!) {
#           jobBoardWithTeams(
#             organizationHostedJobsPageName: $organizationHostedJobsPageName
#           ) {
#             jobPostings {
#               id
#               title
#               locationName
#               postedAt
#               externalLink
#               descriptionHtml
#             }
#           }
#         }
#         """
#     }

#     jobs = []
#     try:
#         r = httpx.post(url, json=payload, timeout=20)
#         r.raise_for_status()
#         data = r.json()

#         postings = data["data"]["jobBoardWithTeams"]["jobPostings"]
#         for j in postings:
#             jobs.append({
#                 "title": j["title"],
#                 "company": company_name,
#                 "location": j.get("locationName"),
#                 "description": j.get("descriptionHtml"),
#                 "apply_url": j.get("externalLink"),
#                 "external_job_id": j["id"],
#                 "posted_at": j.get("postedAt"),
#                 "raw": j,
#                 "logo": logo,
#             })

#     except Exception:
#         logger.exception("Ashby fetch failed for %s", company_name)

#     return jobs
