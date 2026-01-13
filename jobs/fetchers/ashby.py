import httpx
import logging
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


def clean_html_to_text(html_content):
    """
    Convert HTML content to clean plain text.
    Removes all HTML tags and normalizes whitespace.
    """
    if not html_content:
        return ""
    
    try:
        soup = BeautifulSoup(str(html_content), "html.parser")
        text = soup.get_text(separator="\n")
        
        # Normalize whitespace
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(line for line in lines if line)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    except Exception as e:
        logger.warning(f"Error cleaning HTML: {e}")
        # Fallback: try to remove HTML tags with regex
        text = re.sub(r'<[^>]+>', '', str(html_content))
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

ASHBY_API_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"


def fetch_ashby(handle: str, company_name: str, logo: str = ""):
    """
    Fetch jobs from AshbyHQ (legal, public job boards)
    Example handle: notion → https://jobs.ashbyhq.com/notion
    """

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
        r = httpx.post(ASHBY_API_URL, json=payload, timeout=20)
        r.raise_for_status()

        data = r.json()
        postings = data["data"]["jobBoardWithTeams"]["jobPostings"]

        for job in postings:
            html_desc = job.get("descriptionHtml") or ""
            clean_desc = clean_html_to_text(html_desc)
            jobs.append({
                "title": job["title"],
                "company": company_name,
                "location": job.get("locationName"),
                "description": clean_desc,
                "apply_url": job.get("externalLink"),
                "external_job_id": job["id"],
                "posted_at": job.get("postedAt"),
                "raw": {
                    "source": "ashby",
                    "company_logo": logo,
                    "ashby_id": job["id"],
                },
            })

    except Exception:
        logger.exception("Ashby fetch failed for %s", company_name)

    return jobs
