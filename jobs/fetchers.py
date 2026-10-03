import httpx
from bs4 import BeautifulSoup
from .utils import parse_date, robots_allowed
import logging
from urllib.parse import urljoin, urlparse
import feedparser
from django.utils import timezone
from datetime import timedelta
import html
import json
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
    url = f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs?content=true"
    jobs = []
    try:
        r = safe_get(url, timeout=30)
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

            # Greenhouse returns HTML entity-escaped content (&lt;p&gt;...)
            text_desc = clean_html_to_text(html.unescape(content or ""))
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
                "workplace_type": (job.get("categories") or {}).get("commitment"),
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


# jobs.ge blocks non-browser user agents (HTTP 410); use a normal browser UA.
JOBS_GE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ka,en;q=0.8",
}
JOBS_GE_IT_LIST_URL = "https://jobs.ge/?cid=6"  # IT / Programming (full category, single page)
JOBS_GE_ENGLISH_STUB_MARKER = "იხილეთ ამ განცხადების სრული ტექსტი ინგლისურ ენაზე"
# Postings that only say "open this link for details" — no real duties/requirements on jobs.ge.
_JOBS_GE_EXTERNAL_DETAIL_PHRASES = (
    "დეტალური ინფორმაციის გასაცნობად",
    "დეტალურად სანახავად",
    "მიჰყევით ბმულს",
    "გთხოვთ ეწვიოთ მოცემულ ბმულს",
    "ვაკანსიის შესახებ დეტალური ინფორმაციის",
    "აპლიკაციის გამოსაგზავნად, მიჰყევით",
    "დეტალების სანახავად ეწვიეთ",
)
# Signals that the posting itself contains duties / requirements we can store.
_JOBS_GE_DETAIL_MARKERS = (
    "მოვალეობ",
    "მოთხოვნ",
    "კვალიფიკაც",
    "გამოცდილებ",
    "პასუხისმგებლ",
    "უნარ-ჩვევ",
    "აუცილებელი მოთხოვნ",
    "სასურველი მოთხოვნ",
    "ძირითადი ამოცან",
    "სამუშაო ამოცან",
    "responsibilities",
    "requirements",
    "qualifications",
    "must have",
    "nice to have",
    "you will",
    "we expect",
    "we are looking",
    "required skills",
    "key duties",
    "what you will do",
    "what you'll do",
)
_JOBS_GE_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_JOBS_GE_URL_RE = re.compile(r"https?://[^\s<>\"'\]\)]+")
_JOBS_GE_EXCLUDE_HOST_FRAGMENTS = (
    "jobs.ge",
    "facebook.com",
    "fb.com",
    "taya.ge",
    "top.ge",
    "netgazeti",
    "twitter.com",
    "x.com",
    "linkedin.com/share",
    "addtoany",
)


_JOBS_GE_CITY_MAP = {
    "თბილისი": "Tbilisi",
    "ბათუმი": "Batumi",
    "ქუთაისი": "Kutaisi",
    "რუსთავი": "Rustavi",
    "ზუგდიდი": "Zugdidi",
    "ფოთი": "Poti",
    "გორი": "Gori",
    "თელავი": "Telavi",
    "ოზურგეთი": "Ozurgeti",
    "ზესტაფონი": "Zestafoni",
    "ქობულეთი": "Kobuleti",
    "tbilisi": "Tbilisi",
    "batumi": "Batumi",
    "kutaisi": "Kutaisi",
    "rustavi": "Rustavi",
    "zugdidi": "Zugdidi",
}


def _jobs_ge_extract_location(description: str) -> tuple[str | None, str]:
    """
    Return (city, country) for a jobs.ge posting.
    City from სამუშაო ადგილი / ადგილმდებარეობა / Location / known Georgian city names;
    country is always Georgia.
    """
    text = description or ""
    place_line = ""
    for pat in (
        r"სამუშაო ადგილ[^\n:]*[:：]\s*([^\n]+)",
        r"ადგილმდებარეობ[^\n:]*[:：]\s*([^\n]+)",
        r"(?i)(?:location|based in|office)[:：]\s*([^\n]+)",
    ):
        m = re.search(pat, text)
        if m:
            place_line = m.group(1).strip().lstrip("*").strip()
            break

    def _city_mentioned(name: str, blob: str) -> bool:
        # Avoid substring false positives (e.g. გორი inside კატეგორია)
        return bool(
            re.search(
                rf"(?<![ა-ჰA-Za-z]){re.escape(name)}(?![ა-ჰA-Za-z])",
                blob,
                flags=re.IGNORECASE,
            )
        )

    # Prefer the dedicated place line, then fall back to the full description.
    for blob in (place_line, text[:2000]):
        if not blob:
            continue
        for ge_name, en_name in _JOBS_GE_CITY_MAP.items():
            if _city_mentioned(ge_name, blob):
                return en_name, "Georgia"

    if place_line:
        # Explicit remote / hybrid wording on the place line
        if re.search(r"(?i)remote|დისტანც|ონლაინ|online|wfh", place_line):
            return "Remote", "Georgia"
        head = re.split(r"[,.]", place_line, maxsplit=1)[0]
        head = re.sub(r"^(?:ქ\.|ქალაქი|\*\*)\s*", "", head.strip(), flags=re.I).strip()
        if head:
            mapped = _JOBS_GE_CITY_MAP.get(head.lower()) or _JOBS_GE_CITY_MAP.get(head)
            if mapped:
                return mapped, "Georgia"
            # Latin city already (e.g. Tbilisi) — only accept known map values
            for en_name in set(_JOBS_GE_CITY_MAP.values()):
                if head.lower() == en_name.lower():
                    return en_name, "Georgia"

    if re.search(r"(?i)(?:\bremote\b|დისტანციურ|მუშაობა დისტანც)", text[:2000]):
        # Only if no onsite city was found above
        return "Remote", "Georgia"

    return None, "Georgia"


_JOBS_GE_MONTHS = {
    "იანვარი": 1, "თებერვალი": 2, "მარტი": 3, "აპრილი": 4, "მაისი": 5, "ივნისი": 6,
    "ივლისი": 7, "აგვისტო": 8, "სექტემბერი": 9, "ოქტომბერი": 10, "ნოემბერი": 11, "დეკემბერი": 12,
}


def _jobs_ge_parse_published(text: str, now=None):
    """Parse jobs.ge listing dates like '03 ოქტომბერი' (no year) into an aware datetime."""
    m = re.match(r"\s*(\d{1,2})\s+(\S+)", text or "")
    if not m:
        return None
    month = _JOBS_GE_MONTHS.get(m.group(2))
    if not month:
        return None
    now = now or timezone.now()
    day = int(m.group(1))
    try:
        published = now.replace(month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
        # A date later than today belongs to last year (e.g. '28 დეკემბერი' seen in January)
        if published > now + timedelta(days=1):
            published = published.replace(year=now.year - 1)
    except ValueError:
        return None
    return published


def _jobs_ge_get(url, timeout=20):
    r = httpx.get(url, headers=JOBS_GE_HEADERS, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r


def _jobs_ge_is_excluded_url(url: str) -> bool:
    lower = (url or "").lower()
    return any(frag in lower for frag in _JOBS_GE_EXCLUDE_HOST_FRAGMENTS)


def _jobs_ge_is_homepage_url(url: str) -> bool:
    """True for bare company sites like https://example.ge/ with no application path."""
    try:
        parsed = urlparse(url)
        path = (parsed.path or "").rstrip("/")
        return path == "" and not parsed.query
    except Exception:
        return False


def _jobs_ge_is_english_stub(page_text: str) -> bool:
    """Georgian stub posts that only point readers to the English version."""
    normalized = re.sub(r"\s+", " ", page_text or "").strip()
    return JOBS_GE_ENGLISH_STUB_MARKER in normalized


def _jobs_ge_core_description(description: str) -> str:
    """Strip jobs.ge header chrome so we can judge whether the body has real detail."""
    skip_prefixes = (
        "დასახელება",
        "მომწოდებელი",
        "გამოქვეყნდა",
        "ბოლო ვადა",
        "ყველა ვაკანსია",
        "ამ ორგანიზაციის",
        "ამოსაბეჭდი",
    )
    lines = []
    for raw in (description or "").split("\n"):
        line = raw.strip()
        if not line or line == "/":
            continue
        if line.startswith(skip_prefixes):
            continue
        lines.append(line)
    return "\n".join(lines)


def _jobs_ge_has_sufficient_detail(description: str) -> bool:
    """
    Keep only postings that include real duties/requirements on jobs.ge itself.

    Skip thin ads that only say "see details / send CV via this link" — those cannot
    populate responsibilities/qualifications usefully.
    """
    if not description or not description.strip():
        return False

    core = _jobs_ge_core_description(description)
    if not core:
        return False

    core_lower = core.lower()
    has_detail_markers = any(
        (m.lower() in core_lower) if all(ord(c) < 128 for c in m) else (m in core)
        for m in _JOBS_GE_DETAIL_MARKERS
    )
    points_to_external = any(p in description for p in _JOBS_GE_EXTERNAL_DETAIL_PHRASES)
    bullet_count = len(re.findall(r"(?:^|\n)\s*(?:\*\*|[-•▪])\s*\S", core))

    if points_to_external and not has_detail_markers and bullet_count < 3:
        return False
    if has_detail_markers:
        return True
    if bullet_count >= 3 and len(core) >= 400:
        return True
    # No structured duties/requirements and short body → not enough info
    if len(core) < 600:
        return False
    # Long marketing copy without duty/requirement markers (e.g. some campus ads)
    return False


def _jobs_ge_extract_apply_contacts(soup: BeautifulSoup, page_text: str):
    """
    Return (apply_url, apply_email) from a jobs.ge detail page.
    Prefer an external registration / application URL; fall back to email.
    """
    apply_url = None
    apply_email = None

    candidate_urls = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?", 1)[0].strip()
            if addr and not apply_email:
                apply_email = addr
            continue
        if href.startswith("http") and not _jobs_ge_is_excluded_url(href):
            candidate_urls.append(href)

    for match in _JOBS_GE_URL_RE.findall(page_text or ""):
        cleaned = match.rstrip(".,;:)")
        if cleaned.startswith("http") and not _jobs_ge_is_excluded_url(cleaned):
            if cleaned not in candidate_urls:
                candidate_urls.append(cleaned)

    # Prefer known application / ATS hosts over generic company sites.
    high_priority = (
        "selfrecruit",
        "personio",
        "greenhouse",
        "lever.co",
        "ashbyhq",
        "workable",
        "smartrecruiters",
        "bamboohr",
        "recruitee",
        "epa.ms",
        "forms.gle",
        "docs.google.com/forms",
        "hel-ai.com/apply",
        "wrk.ge/",
    )
    mid_priority = ("/apply", "/career", "recruit", "/job/", "/jobs/", "/s/")
    for url in candidate_urls:
        lower = url.lower()
        if any(frag in lower for frag in high_priority):
            apply_url = url
            break
    if not apply_url:
        for url in candidate_urls:
            lower = url.lower()
            if _jobs_ge_is_homepage_url(url):
                continue
            if any(frag in lower for frag in mid_priority):
                apply_url = url
                break

    if not apply_email:
        for match in _JOBS_GE_EMAIL_RE.findall(page_text or ""):
            if match.lower().endswith("@jobs.ge"):
                continue
            apply_email = match
            break

    # Only fall back to a non-homepage external link when there is no email.
    # Company logos/homepages (monitori.ge, publika.ge, …) are not apply links.
    if not apply_url and not apply_email:
        for url in candidate_urls:
            if not _jobs_ge_is_homepage_url(url):
                apply_url = url
                break

    return apply_url, apply_email


def _jobs_ge_parse_listing(soup: BeautifulSoup):
    """Parse all IT listing rows from a jobs.ge category page (vip + regular)."""
    listings = []
    seen = set()
    # Prefer entry tables; fall back to any job link on the page so we never miss ads.
    anchors = soup.select(
        "div.regularEntries a[href*='view=jobs'][href*='id='], "
        "div.vipEntries a[href*='view=jobs'][href*='id='], "
        "a[href*='view=jobs'][href*='id=']"
    )
    for a in anchors:
        href = a.get("href") or ""
        m = re.search(r"[?&]id=(\d+)", href)
        if not m:
            continue
        job_id = m.group(1)
        if job_id in seen:
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        seen.add(job_id)

        company = ""
        published = ""
        deadline = ""
        tr = a.find_parent("tr")
        if tr:
            client = tr.find("a", href=re.compile(r"view=client"))
            if client:
                company = client.get_text(" ", strip=True)
            tds = tr.find_all("td")
            if len(tds) >= 6:
                if not company:
                    company = tds[3].get_text(" ", strip=True)
                published = tds[4].get_text(" ", strip=True)
                deadline = tds[5].get_text(" ", strip=True)

        detail_url = href if href.startswith("http") else urljoin(BASE_URL, href)
        listings.append({
            "external_job_id": job_id,
            "title": title,
            "company": company,
            "published": published,
            "deadline": deadline,
            "detail_url": detail_url,
        })
    return listings


def fetch_jobs_ge_listings(
    list_url=None,
    company_name="Jobs.ge IT",
    logo=None,
    limit=None,
):
    """
    Fetch every tech (IT/Programming, cid=6) job from jobs.ge.

    For each listing, opens the detail page and extracts:
    - apply_url: real registration / application link when present
    - apply_email: HR email when the posting asks to email a CV
    Skips English-only stubs and thin ads that only link out for details
    (no responsibilities/qualifications content on the page).
    """
    list_url = list_url or JOBS_GE_IT_LIST_URL
    logo = logo or get_logo_url(company_name)
    jobs = []
    try:
        if not robots_allowed(list_url):
            logger.warning("Scraping disallowed by robots.txt: %s", list_url)
            return jobs

        r = _jobs_ge_get(list_url)
        soup = BeautifulSoup(r.content, "html.parser")
        listings = _jobs_ge_parse_listing(soup)
        if limit is not None:
            listings = listings[:limit]

        logger.info("jobs.ge: found %s IT listings at %s", len(listings), list_url)
        skipped_thin = 0
        skipped_english = 0

        for item in listings:
            detail_url = item["detail_url"]
            try:
                detail_r = _jobs_ge_get(detail_url)
            except Exception as e:
                logger.warning("jobs.ge: failed to fetch detail %s: %s", detail_url, e)
                continue

            detail_soup = BeautifulSoup(detail_r.content, "html.parser")
            page_text = detail_soup.get_text("\n", strip=True)

            if _jobs_ge_is_english_stub(page_text):
                skipped_english += 1
                logger.info(
                    "jobs.ge: skipping English-stub posting %s (%s)",
                    item["external_job_id"],
                    item["title"],
                )
                continue

            apply_url, apply_email = _jobs_ge_extract_apply_contacts(detail_soup, page_text)

            # Prefer the posting body table; fall back to full page text.
            body_el = detail_soup.select_one("table.dtable") or detail_soup.select_one(".dtable")
            if body_el:
                description = clean_html_to_text(str(body_el))
            else:
                description = page_text
                for marker in ("ყველა ვაკანსია", "დასახელება:"):
                    idx = description.find(marker)
                    if idx >= 0:
                        description = description[idx:]
                        break
                for end_marker in ("გადაიტანე Facebook-ზე", "© 1998"):
                    idx = description.find(end_marker)
                    if idx > 0:
                        description = description[:idx]
                        break
                description = description.strip()

            if not _jobs_ge_has_sufficient_detail(description):
                skipped_thin += 1
                logger.info(
                    "jobs.ge: skipping thin posting without duties/requirements %s (%s)",
                    item["external_job_id"],
                    item["title"],
                )
                continue

            city, country = _jobs_ge_extract_location(description)
            company = (item.get("company") or company_name).strip() or company_name
            jobs.append({
                "title": item["title"],
                "company": company,
                "location": city,
                "location_country": country,
                "description": description or None,
                "apply_url": apply_url,
                "apply_email": apply_email,
                "posted_at": _jobs_ge_parse_published(item.get("published")),
                "platform": "jobs.ge",
                "external_job_id": item["external_job_id"],
                "raw": {
                    "source_url": detail_url,
                    "published": item.get("published"),
                    "deadline": item.get("deadline"),
                    "apply_email": apply_email,
                    "location_raw": city,
                },
                "logo": get_logo_url(company) if company != company_name else logo,
            })

        logger.info(
            "jobs.ge: kept %s jobs (skipped thin=%s, english_stub=%s) from %s listings",
            len(jobs),
            skipped_thin,
            skipped_english,
            len(listings),
        )
    except Exception:
        logger.exception("jobs.ge fetch failed for %s", list_url)
    return jobs


def fetch_ashby(handle: str, company_name: str, logo=None):
    """
    Fetch jobs from AshbyHQ public job board.

    List endpoint returns brief postings (title/location/workplaceType). Detail pages
    expose description + schema.org applicantLocationRequirements (country eligibility).
    """
    import httpx
    logo = logo or get_logo_url(company_name)
    list_url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
    list_payload = {
        "operationName": "ApiJobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": handle},
        "query": """
        query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
          jobBoardWithTeams(
            organizationHostedJobsPageName: $organizationHostedJobsPageName
          ) {
            jobPostings {
              id
              title
              locationName
              employmentType
              workplaceType
            }
          }
        }
        """,
    }

    jobs = []
    try:
        r = httpx.post(list_url, json=list_payload, timeout=25, headers=HEADERS)
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            logger.warning("Ashby GraphQL errors for %s: %s", company_name, data["errors"])
        board = (data.get("data") or {}).get("jobBoardWithTeams") or {}
        postings = board.get("jobPostings") or []

        for j in postings:
            job_id = str(j.get("id") or "").strip()
            if not job_id:
                continue
            title = (j.get("title") or "").strip()
            location = (j.get("locationName") or "").strip()
            workplace = (j.get("workplaceType") or "").strip()
            detail_url = f"https://jobs.ashbyhq.com/{handle}/{job_id}"

            # Skip obvious onsite/hybrid before hitting detail pages — they can't pass
            # the worldwide-remote filter.
            wt_l = workplace.lower()
            loc_l = location.lower()
            looks_remote = wt_l == "remote" or "remote" in loc_l or "distributed" in loc_l
            if wt_l in {"onsite", "hybrid"} and not looks_remote:
                continue
            if not looks_remote and wt_l and wt_l != "remote":
                continue
            if not looks_remote and location and "remote" not in loc_l:
                # City-only listings without Remote workplaceType
                continue

            description = ""
            applicant_reqs = None
            try:
                detail_r = httpx.get(
                    detail_url,
                    timeout=20,
                    headers=JOBS_GE_HEADERS,
                    follow_redirects=True,
                )
                detail_r.raise_for_status()
                detail_soup = BeautifulSoup(detail_r.content, "html.parser")
                for script in detail_soup.select('script[type="application/ld+json"]'):
                    raw_json = script.string or script.get_text() or ""
                    try:
                        ld = json.loads(raw_json)
                    except Exception:
                        continue
                    if not isinstance(ld, dict):
                        continue
                    if not (ld.get("description") or ld.get("applicantLocationRequirements") is not None):
                        continue
                    description = clean_html_to_text(ld.get("description") or description)
                    applicant_reqs = ld.get("applicantLocationRequirements") or applicant_reqs
                    if ld.get("jobLocationType") == "TELECOMMUTE" and not workplace:
                        workplace = "Remote"
                    break
                if not description:
                    description = clean_html_to_text(
                        detail_soup.select_one("[class*='description'], main, article") or ""
                    )
            except Exception as e:
                logger.warning("Ashby detail fetch failed for %s (%s): %s", company_name, job_id, e)

            jobs.append({
                "title": title,
                "company": company_name,
                "location": location,
                "description": description,
                "apply_url": detail_url,
                "external_job_id": job_id,
                "posted_at": None,
                "platform": "ashby",
                "workplace_type": workplace or None,
                "applicant_location_requirements": applicant_reqs,
                "raw": {
                    **j,
                    "applicantLocationRequirements": applicant_reqs,
                    "source_url": detail_url,
                },
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
                    "workplace_type": "Remote",
                    "external_job_id": str(jid),
                    "raw": {
                        **job,
                        "source": "Remotive",
                        "remotive_terms": "https://remotive.com/api-documentation",
                        "candidate_required_location": loc,
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
