import httpx
import logging

logger = logging.getLogger(__name__)

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
            jobs.append({
                "title": job["title"],
                "company": company_name,
                "location": job.get("locationName"),
                "description": job.get("descriptionHtml"),
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
