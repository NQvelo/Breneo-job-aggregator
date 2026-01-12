import re
import logging
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from django.utils import timezone
import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


def robots_allowed(url, user_agent="*"):
    """
    Check if robots.txt allows fetching the URL.
    Returns True if allowed, False if disallowed, or True if robots.txt is unavailable.
    """
    try:
        from urllib.robotparser import RobotFileParser
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        # If robots.txt check fails, allow by default
        return True


def parse_date(date_str):
    """Parse various date formats into a datetime object."""
    if not date_str:
        return None
    try:
        return date_parser.parse(str(date_str))
    except Exception:
        return None


def parse_structured_description(description_text):
    """
    Parse job description text to extract structured information.
    Returns a dictionary with extracted fields.
    """
    if not description_text:
        return {}
    
    structured = {}
    
    # Extract salary information
    salary_patterns = [
        r'\$(\d{1,3}(?:,\d{3})*(?:k|K)?)\s*-\s*\$(\d{1,3}(?:,\d{3})*(?:k|K)?)',
        r'\$(\d{1,3}(?:,\d{3})*(?:k|K)?)\s*(?:per|/)\s*(?:year|month|hour)',
        r'(\d{1,3}(?:,\d{3})*(?:k|K)?)\s*-\s*(\d{1,3}(?:,\d{3})*(?:k|K)?)\s*USD',
    ]
    for pattern in salary_patterns:
        match = re.search(pattern, description_text, re.IGNORECASE)
        if match:
            structured['salary'] = match.group(0)
            break
    
    # Extract location information
    location_patterns = [
        r'(Remote|Hybrid|On-site|Onsite)',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z]{2})',  # City, State
    ]
    locations = []
    for pattern in location_patterns:
        matches = re.findall(pattern, description_text)
        locations.extend(matches)
    if locations:
        structured['locations'] = locations
    
    # Extract requirements/skills
    skills_keywords = ['Python', 'JavaScript', 'React', 'Node.js', 'AWS', 'Docker', 'Kubernetes']
    found_skills = [skill for skill in skills_keywords if skill.lower() in description_text.lower()]
    if found_skills:
        structured['skills'] = found_skills
    
    return structured


def fetch_company_info_from_web(company_name, domain=None):
    """
    Scrape company website to extract basic information.
    Falls back to Wikipedia if website scraping fails.
    """
    info = {}
    
    # Try to get domain from company name if not provided
    if not domain:
        # Try common domain patterns - be smarter about company name matching
        safe_name = company_name.lower().replace(" ", "").replace(".", "").replace(",", "").replace("-", "")
        # Remove common suffixes
        safe_name = re.sub(r'(inc|llc|corp|ltd|company)$', '', safe_name)
        
        potential_domains = [
            f"{safe_name}.com",
            f"{safe_name}.io",
            f"{safe_name}.co",
            f"{safe_name}.ai",
        ]
    else:
        potential_domains = [domain] if not domain.startswith("http") else [domain]
    
    # Try scraping company website
    for potential_domain in potential_domains:
        if not potential_domain.startswith("http"):
            potential_domain = f"https://{potential_domain}"
        
        try:
            if not robots_allowed(potential_domain):
                continue
            
            # Use allow_redirects but check final URL matches company name
            response = httpx.get(potential_domain, headers=HEADERS, timeout=10, follow_redirects=True)
            if response.status_code == 200:
                parsed_url = urlparse(response.url)
                final_domain = parsed_url.netloc.replace("www.", "").lower()
                
                # Verify the domain matches the company name (basic check)
                company_name_lower = company_name.lower().replace(" ", "").replace(".", "").replace("-", "")
                domain_base = final_domain.split(".")[0]
                
                # Skip if redirected to unrelated domains (like nasdaq.com, linkedin.com, etc.)
                skip_domains = ["nasdaq", "linkedin", "crunchbase", "wikipedia", "twitter", "facebook", "github", 
                               "bloomberg", "reuters", "techcrunch", "medium", "substack"]
                if any(skip in final_domain for skip in skip_domains):
                    continue
                
                # Only store domain/website if it matches the company name (to avoid storing source sites)
                if company_name_lower not in domain_base and domain_base not in company_name_lower:
                    # Domain doesn't match company name - skip it to avoid storing wrong domains
                    continue
                
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Extract domain - only store if we're confident it's the company's domain
                info["domain"] = final_domain
                info["website"] = f"{parsed_url.scheme}://{parsed_url.netloc}"
                
                # Extract description from meta tags
                meta_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
                if meta_desc:
                    desc = meta_desc.get("content", "")
                    if desc and len(desc) > 50:
                        info["description"] = desc[:500]  # Limit to 500 chars
                
                # Try to find "About" section
                about_sections = soup.find_all(["section", "div"], class_=re.compile(r"about|intro|mission", re.I))
                for section in about_sections[:2]:  # Check first 2 sections
                    text = section.get_text(strip=True)
                    if len(text) > 100 and not info.get("description"):
                        info["description"] = text[:500]
                
                # If we got a good match, return early
                if company_name_lower in domain_base or domain_base in company_name_lower:
                    return info
        except Exception as e:
            logger.debug(f"Failed to scrape {potential_domain}: {e}")
            continue
    
    # Return info if we found a valid company domain/website
    if info.get("domain"):
        # Double-check we're not storing a source site domain
        domain = info.get("domain", "").lower()
        skip_domains = ["wikipedia.org", "wikimedia.org", "linkedin.com", "twitter.com", 
                       "facebook.com", "crunchbase.com", "nasdaq.com"]
        if not any(skip in domain for skip in skip_domains):
            return info
    
    # Fallback to Wikipedia (only for description and founded_date, not domain/website)
    try:
        wiki_info = _fetch_from_wikipedia(company_name)
        if wiki_info:
            # Only merge description and founded_date from Wikipedia, not domain/website
            # (domain/website should only come from the company's actual website)
            if not info.get("description") and wiki_info.get("description"):
                info["description"] = wiki_info["description"]
            if not info.get("founded_date") and wiki_info.get("founded_date"):
                info["founded_date"] = wiki_info["founded_date"]
            # Only add domain/website from Wikipedia if it's the company's actual website (already validated in _fetch_from_wikipedia)
            if wiki_info.get("domain") and wiki_info.get("website"):
                info["domain"] = wiki_info["domain"]
                info["website"] = wiki_info["website"]
    except Exception:
        pass
    
    return info if info else None


def _fetch_from_wikipedia(company_name):
    """Fetch company information from Wikipedia."""
    try:
        # Try Wikipedia API
        search_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{company_name.replace(' ', '_')}"
        response = httpx.get(search_url, headers=HEADERS, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            info = {}
            
            if data.get("extract"):
                info["description"] = data["extract"][:500]
            
            # Try to get founded year from infobox
            if "content_urls" in data:
                page_url = data["content_urls"]["desktop"]["page"]
                page_response = httpx.get(page_url, headers=HEADERS, timeout=10)
                if page_response.status_code == 200:
                    soup = BeautifulSoup(page_response.text, "html.parser")
                    infobox = soup.find("table", class_="infobox")
                    if infobox:
                        # Look for founded year
                        for row in infobox.find_all("tr"):
                            header = row.find("th")
                            if header and "founded" in header.get_text().lower():
                                value = row.find("td")
                                if value:
                                    year_match = re.search(r'\b(19|20)\d{2}\b', value.get_text())
                                    if year_match:
                                        info["founded_date"] = _parse_founded_date(year_match.group(0))
    
                        # Look for website - only extract company's actual website, not Wikipedia or other source sites
                        website_link = infobox.find("a", href=re.compile(r'^https?://'))
                        if website_link:
                            website_url = website_link.get("href")
                            parsed = urlparse(website_url)
                            website_domain = parsed.netloc.replace("www.", "").lower()
                            
                            # Skip if it's a source site (Wikipedia, LinkedIn, etc.)
                            skip_domains = ["wikipedia.org", "wikimedia.org", "linkedin.com", "twitter.com", 
                                           "facebook.com", "crunchbase.com", "bloomberg.com", "reuters.com"]
                            if any(skip in website_domain for skip in skip_domains):
                                # Don't store source sites as company website
                                pass
                            else:
                                # Store the company's actual website
                                info["website"] = website_url
                                info["domain"] = website_domain
            
            return info if info else None
    except Exception as e:
        logger.debug(f"Wikipedia fetch failed for {company_name}: {e}")
    
    return None


def _format_employee_count(employee_count):
    """Format employee count into readable ranges."""
    if not employee_count:
        return None
    
    try:
        count = int(employee_count)
        if count < 10:
            return "1-10"
        elif count < 50:
            return "11-50"
        elif count < 200:
            return "51-200"
        elif count < 500:
            return "201-500"
        elif count < 1000:
            return "501-1000"
        else:
            return "1000+"
    except (ValueError, TypeError):
        return None


def _parse_founded_date(year_str):
    """Parse founded year string into a date object."""
    if not year_str:
        return None
    
    try:
        year = int(str(year_str).strip())
        if 1800 <= year <= 2100:  # Sanity check
            from datetime import date
            return date(year, 1, 1)  # Use January 1st as default
    except (ValueError, TypeError):
        pass
    
    return None
