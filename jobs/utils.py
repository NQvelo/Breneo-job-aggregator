import httpx
from urllib.parse import urlparse
from dateutil import parser as date_parser

def parse_date(s):
    if not s:
        return None
    try:
        return date_parser.parse(s)
    except Exception:
        return None

def robots_allowed(url, user_agent="*"):
    """
    Basic robots.txt check: returns True if allowed to fetch path.
    Very lightweight: fetches robots.txt each time (can be cached).
    """
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        r = httpx.get(robots_url, timeout=5)
        if r.status_code != 200:
            return True  # assume allowed when robots missing
        txt = r.text.lower()
        # This is a simple heuristic — not a full robots parser.
        # If 'disallow: /' exists and no allow override, deny.
        path = parsed.path.lower()
        if "disallow: /" in txt and f"disallow: {path}" in txt:
            return False
        return True
    except Exception:
        return True
