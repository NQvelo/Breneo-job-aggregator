import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://jobs.ge"


def fetch_jobs_ge(limit=20):
    jobs = []
    url = f"{BASE_URL}/en/?page=1"

    res = httpx.get(url, timeout=10, headers={"User-Agent": "Breneo Job Aggregator (research purposes)"})
    if res.status_code != 200:
        return jobs

    soup = BeautifulSoup(res.text, "html.parser")
    job_cards = soup.select(".job-item")[:limit]

    for card in job_cards:
        title_el = card.select_one(".job-title a")
        company_el = card.select_one(".company-name")

        if not title_el:
            continue

        href = title_el.get("href")
        full_url = href if href.startswith("http") else urljoin(BASE_URL, href)

        jobs.append({
            "external_job_id": full_url,
            "title": title_el.text.strip(),
            "company": company_el.text.strip() if company_el else "Unknown",
            "location": "Georgia",
            "description": None,
            "apply_url": full_url,
            "posted_at": None,
            "platform": "jobs.ge",
            "raw": {},
        })

    return jobs
