import httpx
from bs4 import BeautifulSoup
from .utils import parse_date, robots_allowed
import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

HEADERS = {"User-Agent": "BreneoJobAggregator/1.0 (+https://yourdomain.example)"}

LOGO_DEV_PUBLIC_KEY = "pk_K96TtQYUTvy3hHXDyIEUqw"

def safe_get(url, timeout=8):
    r = httpx.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r

def get_logo_url(company_name: str, size=101) -> str:
    safe_name = company_name.replace(" ", "")
    return f"https://img.logo.dev/name/{safe_name}?token={LOGO_DEV_PUBLIC_KEY}&size={size}&retina=true"


def fetch_greenhouse(handle, company_name):
    logo = get_logo_url(company_name)
    url = f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs"
    jobs = []
    try:
        r = safe_get(url)
        data = r.json()
        for job in data.get("jobs", []):
            job_id = job.get("id")
            absolute_url = job.get("absolute_url") or f"https://boards.greenhouse.io/{handle}/jobs/{job_id}"
            content = job.get("content", "")
            text_desc = BeautifulSoup(content or "", "html.parser").get_text(separator="\n").strip()
            jobs.append({
                "title": job.get("title") or "",
                "company": company_name,
                "location": (job.get("location") or {}).get("name", ""),
                "description": text_desc,
                "apply_url": absolute_url,
                "posted_at": parse_date(job.get("updated_at") or job.get("created_at")),
                "platform": "greenhouse",
                "external_job_id": str(job_id),
                "raw": job,
                "logo": logo,
            })
    except Exception:
        logger.exception("Greenhouse fetch error for %s (%s)", company_name, handle)
    return jobs


def fetch_lever(handle, company_name):
    logo = get_logo_url(company_name)
    url = f"https://api.lever.co/v0/postings/{handle}?mode=json"
    jobs = []
    try:
        r = safe_get(url)
        data = r.json()
        for job in data:
            job_id = job.get("id") or job.get("uuid") or job.get("postingId")
            hosted_url = job.get("hostedUrl") or job.get("applyUrl") or job.get("url")
            html_desc = job.get("description") or ""
            text_desc = BeautifulSoup(html_desc, "html.parser").get_text(separator="\n").strip()
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


def fetch_workable(company_slug, company_name):
    logo = get_logo_url(company_name)
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
                "description": BeautifulSoup(desc, "html.parser").get_text(),
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


def fetch_rss(feed_url, company_name):
    import feedparser
    logo = get_logo_url(company_name)
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
                "description": BeautifulSoup(desc, "html.parser").get_text(),
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


def fetch_generic_career_page(list_url, company_name, selector=None):
    logo = get_logo_url(company_name)
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

BASE_URL = "https://jobs.ge"


def fetch_jobs_ge_listings(list_url, company_name="Local Georgian", logo=None, limit=20):
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

def fetch_ashby(handle: str, company_name: str):
    """
    Fetch jobs from AshbyHQ
    Example: https://jobs.ashbyhq.com/notion
    """
    import httpx
    logo = get_logo_url(company_name)

    url = f"https://jobs.ashbyhq.com/api/non-user-graphql"
    payload = {
        "operationName": "JobBoardWithTeams",
        "variables": {
            "organizationHostedJobsPageName": handle
        },
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
            jobs.append({
                "title": j["title"],
                "company": company_name,
                "location": j.get("locationName"),
                "description": j.get("descriptionHtml"),
                "apply_url": j.get("externalLink"),
                "external_job_id": j["id"],
                "posted_at": j.get("postedAt"),
                "raw": j,
                "logo": logo,
            })

    except Exception:
        logger.exception("Ashby fetch failed for %s", company_name)

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
