from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import httpx
from bs4 import BeautifulSoup

app = FastAPI(title="Job Aggregator API")

# ----------------------
# Job data model
# ----------------------
class Job(BaseModel):
    title: str
    company: str
    location: str
    apply_url: str
    platform: str

# ----------------------
# Fetch jobs from Greenhouse
# ----------------------
async def fetch_greenhouse_jobs(company: str) -> List[Job]:
    url = f"https://boards.greenhouse.io/api/v1/boards/{company}/jobs"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        jobs = [
            Job(
                title=j["title"],
                company=company,
                location=j.get("location", {}).get("name", "Remote"),
                apply_url=f"https://boards.greenhouse.io/{company}/jobs/{j['id']}",
                platform="greenhouse"
            )
            for j in data.get("jobs", [])
        ]
        return jobs
    except Exception as e:
        print(f"Greenhouse error for {company}: {e}")
        return []

# ----------------------
# Fetch jobs from generic career page
# ----------------------
async def fetch_career_page_jobs(url: str, company: str) -> List[Job]:
    try:
        async with httpx.AsyncClient() as client:
            html = await client.get(url, timeout=10)
        soup = BeautifulSoup(html.text, "html.parser")
        jobs = [
            Job(
                title=job.text.strip(),
                company=company,
                location="Unknown",
                apply_url=job['href'],
                platform="career_page"
            )
            for job in soup.select("a.job-link")
        ]
        return jobs
    except Exception as e:
        print(f"Career page error for {company}: {e}")
        return []

# ----------------------
# API endpoint
# ----------------------


GREENHOUSE_COMPANIES = ["stripe", "airbnb", "doordash", "spacex", "cloudflare"]


@app.get("/jobs", response_model=List[Job])
async def get_jobs():
    all_jobs = []

    # Fetch jobs from multiple Greenhouse companies
    for company in GREENHOUSE_COMPANIES:
        all_jobs.extend(await fetch_greenhouse_jobs(company))

    # Example: Add generic career pages
    all_jobs.extend(await fetch_career_page_jobs("https://example.com/careers", "ExampleCorp"))

    return all_jobs

