from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import httpx
from bs4 import BeautifulSoup

app = FastAPI(title="Job Aggregator API")

# ----------------------
# Job data model
# ----------------------
class Company(BaseModel):
    id: str              # slug like "figma", "stripe"
    name: str
    logo: str | None = None
    platform: str


class Job(BaseModel):
    title: str
    location: str
    apply_url: str
    platform: str
    external_job_id: str
    company: Company


# ----------------------
# Fetch jobs from Greenhouse
# ----------------------
async def fetch_greenhouse_jobs(company_slug: str) -> List[Job]:
    url = f"https://boards.greenhouse.io/api/v1/boards/{company_slug}/jobs"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        company = Company(
            id=company_slug,
            name=company_slug.capitalize(),
            logo=f"https://img.logo.dev/name/{company_slug}?token=pk_K96TtQYUTvy3hHXDyIEUqw",
            platform="greenhouse",
        )

        jobs = [
            Job(
                title=j["title"],
                location=j.get("location", {}).get("name", "Remote"),
                apply_url=f"https://boards.greenhouse.io/{company_slug}/jobs/{j['id']}",
                platform="greenhouse",
                external_job_id=str(j["id"]),
                company=company,
            )
            for j in data.get("jobs", [])
        ]

        return jobs

    except Exception as e:
        print(f"Greenhouse error for {company_slug}: {e}")
        return []

# ----------------------
# Fetch jobs from generic career page
# ----------------------
async def fetch_career_page_jobs(url: str, company_name: str) -> List[Job]:
    try:
        async with httpx.AsyncClient() as client:
            html = await client.get(url, timeout=10)

        soup = BeautifulSoup(html.text, "html.parser")

        company = Company(
            id=company_name.lower(),
            name=company_name,
            platform="career_page",
        )

        jobs = [
            Job(
                title=job.text.strip(),
                location="Unknown",
                apply_url=job["href"],
                platform="career_page",
                external_job_id=job["href"],
                company=company,
            )
            for job in soup.select("a.job-link")
        ]

        return jobs

    except Exception as e:
        print(f"Career page error for {company_name}: {e}")
        return []

# ----------------------
# API endpoint
# ----------------------

GREENHOUSE_COMPANIES = ["stripe", "airbnb", "doordash", "spacex", "cloudflare"]

@app.get("/jobs", response_model=List[Job])
async def get_jobs():
    all_jobs: List[Job] = []

    for company in GREENHOUSE_COMPANIES:
        all_jobs.extend(await fetch_greenhouse_jobs(company))

    all_jobs.extend(
        await fetch_career_page_jobs(
            "https://example.com/careers",
            "ExampleCorp"
        )
    )

    return all_jobs
