import os
import re
import json
import logging
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import httpx

logger = logging.getLogger(__name__)

# Hugging Face model imports (lazy loading to avoid import errors if not installed)
_transformers_available = False
_pipeline = None

try:
    from transformers import pipeline
    _transformers_available = True
except ImportError:
    pass

try:
    from duckduckgo_search import DDGS
    _ddgs_available = True
except ImportError:
    _ddgs_available = False
    logger.warning("duckduckgo-search library not installed. DuckDuckGo AI will be unavailable.")


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


def extract_responsibilities_and_qualifications(description_text):
    """
    Extract responsibilities and qualifications from job description using AI.
    
    Args:
        description_text: Full job description text
        
    Returns:
        tuple: (responsibilities_text, qualifications_text)
    """
    if not description_text:
        return None, None
    
    responsibilities = None
    qualifications = None
    
    # First, try to extract using pattern matching (fast, no AI needed)
    responsibilities, qualifications = _extract_with_patterns(description_text)
    
    # If pattern matching didn't find both sections, use AI
    if not responsibilities or not qualifications:
        try:
            ai_responsibilities, ai_qualifications = _extract_with_ai(description_text)
            if ai_responsibilities and not responsibilities:
                responsibilities = ai_responsibilities
            if ai_qualifications and not qualifications:
                qualifications = ai_qualifications
        except Exception as e:
            logger.warning(f"AI extraction failed: {e}. Using pattern matching results only.")
    
    return responsibilities, qualifications


def _extract_with_patterns(description_text):
    """
    Extract responsibilities and qualifications using pattern matching.
    This is a fast fallback method that looks for common section headers.
    """
    responsibilities = None
    qualifications = None
    
    # Common section headers
    responsibility_patterns = [
        r'(?:responsibilities|what you\'?ll do|key responsibilities|what you will do|role and responsibilities)',
        r'(?:duties|key duties|main responsibilities)',
    ]
    
    qualification_patterns = [
        r'(?:qualifications|requirements|what we\'?re looking for|required qualifications|must have)',
        r'(?:skills|required skills|preferred qualifications|nice to have)',
    ]
    
    # Split text into sections
    lines = description_text.split('\n')
    current_section = None
    current_text = []
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Check if this line is a section header
        is_responsibility_header = any(re.search(pattern, line_lower) for pattern in responsibility_patterns)
        is_qualification_header = any(re.search(pattern, line_lower) for pattern in qualification_patterns)
        
        if is_responsibility_header:
            # Save previous section
            if current_section == 'qualifications' and current_text:
                qualifications = '\n'.join(current_text).strip()
            current_section = 'responsibilities'
            current_text = []
        elif is_qualification_header:
            # Save previous section
            if current_section == 'responsibilities' and current_text:
                responsibilities = '\n'.join(current_text).strip()
            current_section = 'qualifications'
            current_text = []
        elif current_section and line.strip():
            current_text.append(line.strip())
    
    # Save the last section
    if current_section == 'responsibilities' and current_text:
        responsibilities = '\n'.join(current_text).strip()
    elif current_section == 'qualifications' and current_text:
        qualifications = '\n'.join(current_text).strip()
    
    return responsibilities, qualifications


def _extract_with_ai(description_text):
    """
    Placeholder for AI extraction - returns None to use pattern-matching fallback.
    """
    return None, None


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


def process_job_description(description_text):
    """
    Process raw job description text into structured format.
    
    Extracts and normalizes:
    - Summary (5-6 sentences)
    - Company Overview
    - Description
    - Role Description
    - Responsibilities (bullet points)
    - Qualifications (bullet points)
    - Benefits (bullet points, if present)
    - Team Description (if present)
    
    Removes irrelevant sections (legal notices, EEO statements, etc.)
    Merges duplicated sections and rewrites in clear, neutral English.
    
    Args:
        description_text: Raw job description text
        
    Returns:
        dict: Structured data with all extracted fields
    """
    if not description_text:
        return {
            'summary': None,
            'company_overview': None,
            'description': None,
            'role_description': None,
            'responsibilities': None,
            'qualifications': None,
            'benefits': None,
        }
    
    try:
        # Use AI to process the job description
        result = _process_with_ai(description_text)
        if result:
            return result
    except Exception as e:
        logger.warning(f"AI processing failed: {e}. Using fallback method.")
    
    # Fallback: Use pattern matching and basic extraction
    result = _process_with_patterns(description_text)
    if result and result.get("benefits") and not is_valid_benefits_text(result["benefits"]):
        result["benefits"] = None
    return result

def _process_with_ai(description_text):
    """
    Placeholder for AI processing - returns None to use pattern-matching fallback.
    """
    return None


def _parse_ai_response_text(text):
    """
    Parse AI response text to extract structured information.
    Fallback when JSON parsing fails.
    """
    result = {
        'summary': None,
        'company_overview': None,
        'description': None,
        'role_description': None,
        'responsibilities': None,
        'qualifications': None,
        'benefits': None,
    }
    
    # Try to extract sections using keywords
    lines = text.split('\n')
    current_section = None
    current_text = []
    
    for line in lines:
        line_lower = line.lower().strip()
        
        if 'summary' in line_lower and not result['summary']:
            current_section = 'summary'
            current_text = []
        elif 'company overview' in line_lower or 'company' in line_lower:
            if current_section:
                result[current_section] = '\n'.join(current_text).strip() if current_text else None
            current_section = 'company_overview'
            current_text = []
        elif 'role description' in line_lower or 'role' in line_lower:
            if current_section:
                result[current_section] = '\n'.join(current_text).strip() if current_text else None
            current_section = 'role_description'
            current_text = []
        elif 'responsibilities' in line_lower:
            if current_section:
                result[current_section] = '\n'.join(current_text).strip() if current_text else None
            current_section = 'responsibilities'
            current_text = []
        elif 'qualifications' in line_lower or 'requirements' in line_lower:
            if current_section:
                result[current_section] = '\n'.join(current_text).strip() if current_text else None
            current_section = 'qualifications'
            current_text = []
        elif 'benefits' in line_lower:
            if current_section:
                result[current_section] = '\n'.join(current_text).strip() if current_text else None
            current_section = 'benefits'
            current_text = []
        elif current_section and line.strip():
            current_text.append(line.strip())
    
    # Save last section
    if current_section:
        result[current_section] = '\n'.join(current_text).strip() if current_text else None
    
    return result


# Benefits section headings (prefer extracting from these)
_BENEFITS_SECTION_PATTERNS = [
    r'\bbenefits\b',
    r'\bperks\b',
    r'what we offer',
    r'compensation (?:&|and) benefits',
    r"how we'll take care of you",
    r'total rewards',
]

# Keywords for detecting benefits when no explicit section exists
# (Avoid loose terms like "education" or "remote" — they match normal job narrative.)
_BENEFITS_KEYWORDS = [
    'health insurance', 'dental', 'vision', 'medical coverage',
    'pto', 'vacation', 'parental leave', 'paid leave', 'sick leave',
    'equity', 'stock options', '401k', '401(k)', 'retirement',
    'bonus', 'performance bonus', 'annual bonus',
    'flexible work', 'flexible hours',
    'learning budget', 'learning stipend', 'tuition reimbursement', 'tuition assistance', 'training stipend',
    'travel credits', 'gym', 'wellness', 'mental health',
    'free meals', 'catered', 'snacks', 'coffee',
    'unlimited pto', 'unlimited vacation',
]

# Patterns that indicate a line should be excluded from benefits (pay, location, EEO, etc.)
_BENEFITS_EXCLUDE_PATTERNS = [
    r'\$[\d,]+', r'\d+\s*k\s*(?:salary|pay)?', r'\d+\s*-\s*\d+\s*k',
    r'\b(?:usd|eur|gbp)\b', r'\bcompensation\b.*\b\d',
    r'\b(?:remote|hybrid|onsite)\b.*\b(?:only|eligible|required)\b',
    r'\b(?:equal opportunity|eeo|affirmative action|inclusion|accommodation)\b',
    r'\b(?:privacy|legal|disclaimer|applicant)\b',
    r'\bpay\s+range\b',
    r'\bitar\b',
    r'\byour\s+actual\s+level\b',
    r'^base\s*$',
    r'\beducation_required\b',
]


def is_valid_benefits_text(s) -> bool:
    """
    True only if benefits text looks like real perks, not pay stubs / ITAR / ATS placeholders.
    """
    if not s or not str(s).strip():
        return False
    raw = str(s).strip()
    low = raw.lower()
    if any(
        x in low
        for x in (
            "pay range",
            "itar requirement",
            "your actual level",
            "education_required",
            "compensation information",
        )
    ):
        return False
    formatted = _filter_and_format_benefits(raw)
    return bool(formatted and formatted.strip())


def _is_benefit_line_excluded(line: str) -> bool:
    """Return True if line contains pay, location rules, EEO, or legal text."""
    line_lower = line.lower().strip()
    for pattern in _BENEFITS_EXCLUDE_PATTERNS:
        if re.search(pattern, line_lower, re.IGNORECASE):
            return True
    return False


def _filter_and_format_benefits(raw_benefits: str) -> str | None:
    """
    Filter and format benefits: max 5 lines, each ≤120 chars.
    Exclude pay, location, EEO/legal text.
    """
    if not raw_benefits or not raw_benefits.strip():
        return None
    lines = [ln.strip() for ln in raw_benefits.split('\n') if ln.strip()]
    filtered = []
    for ln in lines:
        if _is_benefit_line_excluded(ln):
            continue
        # Trim to 120 chars at word boundary
        if len(ln) > 120:
            truncated = ln[:117].rsplit(' ', 1)[0]
            ln = truncated if len(truncated) > 50 else ln[:120]
        filtered.append(ln)
        if len(filtered) >= 5:
            break
    return '\n'.join(filtered).strip() if filtered else None


def _extract_benefits_by_keywords(text: str) -> str | None:
    """Extract benefits using keyword-based rules when no explicit section exists."""
    if not text or not text.strip():
        return None
    text_lower = text.lower()
    found = []
    for kw in _BENEFITS_KEYWORDS:
        if kw in text_lower:
            # Extract a short phrase around the keyword (up to ~80 chars)
            idx = text_lower.find(kw)
            start = max(0, idx - 20)
            end = min(len(text), idx + len(kw) + 60)
            phrase = text[start:end].strip()
            # Clean: take first sentence or clause
            phrase = re.split(r'[.;\n]', phrase)[0].strip()
            if 10 <= len(phrase) <= 120 and not _is_benefit_line_excluded(phrase):
                found.append(phrase)
                if len(found) >= 5:
                    break
    return '\n'.join(found).strip() if found else None


def _process_with_patterns(description_text):
    """
    Fallback method using pattern matching to extract structured information.
    """
    from jobs.job_posting_parser import strip_job_posting_text

    # Strip pay/ITAR/education tails before pattern extraction
    cleaned_text = strip_job_posting_text(description_text or "")
    # Remove irrelevant sections
    cleaned_text = _remove_irrelevant_sections(cleaned_text)
    
    result = {
        'summary': None,
        'company_overview': None,
        'description': cleaned_text[:500] if cleaned_text else None,
        'role_description': None,
        'responsibilities': None,
        'qualifications': None,
        'benefits': None,
    }
    
    # Extract using existing pattern matching
    responsibilities, qualifications = _extract_with_patterns(cleaned_text)
    result['responsibilities'] = responsibilities
    result['qualifications'] = qualifications
    
    # Try to extract benefits from explicit sections (Benefits, Perks, What we offer, etc.)
    benefits_patterns = [
        r'\b(?:benefits|perks|what we offer|compensation (?:&|and) benefits)\b',
        r"(?:how we'll take care of you|total rewards)",
    ]
    
    lines = cleaned_text.split('\n')
    current_section = None
    current_text = []
    
    for line in lines:
        line_lower = line.lower().strip()
        
        if any(re.search(pattern, line_lower) for pattern in benefits_patterns):
            if current_section == 'benefits':
                current_text.append(line.strip())
            else:
                if current_section:
                    result[current_section] = '\n'.join(current_text).strip() if current_text else None
                current_section = 'benefits'
                current_text = []
        elif current_section == 'benefits' and line.strip():
            current_text.append(line.strip())
    
    if current_section == 'benefits' and current_text:
        result['benefits'] = _filter_and_format_benefits('\n'.join(current_text).strip())
    elif not result['benefits']:
        # Keyword-based fallback when no explicit benefits section found
        result['benefits'] = _extract_benefits_by_keywords(cleaned_text)
    if result.get("benefits") and not is_valid_benefits_text(result["benefits"]):
        result["benefits"] = None
    
    # Create summary from first few sentences
    sentences = cleaned_text.split('. ')
    if len(sentences) > 5:
        result['summary'] = '. '.join(sentences[:6]) + '.'
    else:
        result['summary'] = cleaned_text[:300]
    
    return result


def _remove_irrelevant_sections(text):
    """
    Remove irrelevant sections from job description.
    """
    if not text:
        return text
    
    # Patterns for irrelevant sections
    irrelevant_patterns = [
        r'(?i)(equal opportunity|EEO|affirmative action)',
        r'(?i)(privacy policy|privacy notice)',
        r'(?i)(pay transparency|salary transparency)',
        r'(?i)(interview recording|recorded interview)',
        r'(?i)(legal notice|disclaimer)',
        r'(?i)(this job posting|this position).*?(?:\.|$)',
    ]
    
    lines = text.split('\n')
    cleaned_lines = []
    skip_until_next_section = False
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Check if this line starts an irrelevant section
        is_irrelevant = any(re.search(pattern, line_lower) for pattern in irrelevant_patterns)
        
        if is_irrelevant:
            skip_until_next_section = True
            continue
        
        # Stop skipping when we hit a new section (usually a header)
        if skip_until_next_section:
            if line.strip() and (line.strip().isupper() or len(line.strip()) < 50):
                skip_until_next_section = False
            else:
                continue
        
        cleaned_lines.append(line)
    
    cleaned_text = '\n'.join(cleaned_lines)
    
    # Remove long salary disclaimers
    salary_disclaimer_pattern = r'(?i)(salary|compensation).{100,}'
    cleaned_text = re.sub(salary_disclaimer_pattern, '', cleaned_text)
    
    return cleaned_text.strip()


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
