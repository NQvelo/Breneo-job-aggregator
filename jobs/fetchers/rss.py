# jobs/fetchers/rss_fetcher.py
import logging
import feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def clean_html(raw_html):
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(separator="\n").strip()

def fetch_rss(feed_url: str, company_name: str, logo: str | None = None):
    """
    Fetch job entries from an RSS/ATOM feed.
    """
    jobs = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            jobs.append({
                "company": company_name,
                "title": entry.get("title", ""),
                "location": entry.get("location", "") or "",
                "team": "",
                "commitment": "",
                "apply_link": entry.get("link", ""),
                "description": clean_html(entry.get("summary", "") or entry.get("content", "")),
                "posting_date": entry.get("published", "") or entry.get("updated", ""),
                "logo": logo,
                "source": "rss",
                "raw": entry,
            })
    except Exception as e:
        logger.warning("RSS fetch error for %s (%s): %s", company_name, feed_url, e)
    return jobs
