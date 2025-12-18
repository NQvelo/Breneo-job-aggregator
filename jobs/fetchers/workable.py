import httpx

def fetch_workable(company):
    jobs = []
    url = f"https://apply.workable.com/api/v3/accounts/{company}/jobs"

    r = httpx.get(url, timeout=10)
    if r.status_code != 200:
        return jobs

    for j in r.json().get("results", []):
        jobs.append({
            "id": j["id"],
            "title": j["title"],
            "company": j["company"]["name"],
            "location": j["location"]["city"],
            "description": j.get("description"),
            "apply_url": j["shortcode_url"],
            "employment_type": j.get("employment_type"),
            "posting_date": j.get("published_at"),
            "source": "Workable"
        })
    return jobs
