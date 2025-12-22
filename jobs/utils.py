import httpx
from urllib.parse import urlparse
from dateutil import parser as date_parser
from bs4 import BeautifulSoup
import re

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


def parse_structured_description(description_text):
    """
    Parse a job description and extract structured information.
    Returns a dictionary with organized sections.
    """
    if not description_text:
        return {}
    
    # Convert HTML to text if needed
    soup = BeautifulSoup(description_text, "html.parser")
    text = soup.get_text(separator="\n").strip()
    
    structured = {
        "overview": "",
        "responsibilities": [],
        "requirements": [],
        "qualifications": [],
        "benefits": [],
        "skills": [],
        "work_type": None,  # remote, hybrid, on-site
        "experience_level": None,  # entry, mid, senior, etc.
        "salary_range": None,
    }
    
    # Normalize text for pattern matching
    text_lower = text.lower()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    # Extract work type
    if any(word in text_lower for word in ["remote", "fully remote", "work from home", "wfh"]):
        structured["work_type"] = "remote"
    elif any(word in text_lower for word in ["hybrid", "partially remote", "flexible"]):
        structured["work_type"] = "hybrid"
    elif any(word in text_lower for word in ["on-site", "onsite", "on site", "office"]):
        structured["work_type"] = "on-site"
    
    # Extract experience level
    if any(word in text_lower for word in ["senior", "sr.", "lead", "principal", "staff"]):
        structured["experience_level"] = "senior"
    elif any(word in text_lower for word in ["mid-level", "mid level", "mid", "intermediate"]):
        structured["experience_level"] = "mid"
    elif any(word in text_lower for word in ["junior", "jr.", "entry", "entry-level", "associate"]):
        structured["experience_level"] = "entry"
    
    # Extract salary range (common patterns)
    salary_patterns = [
        r'\$(\d{1,3}(?:,\d{3})*(?:k|K)?)\s*[-–—]\s*\$(\d{1,3}(?:,\d{3})*(?:k|K)?)',
        r'\$(\d{1,3}(?:,\d{3})*(?:k|K)?)\s*to\s*\$(\d{1,3}(?:,\d{3})*(?:k|K)?)',
        r'(\d{1,3}(?:,\d{3})*(?:k|K)?)\s*[-–—]\s*(\d{1,3}(?:,\d{3})*(?:k|K)?)\s*(?:USD|usd|\$)',
    ]
    for pattern in salary_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            structured["salary_range"] = f"${match.group(1)} - ${match.group(2)}"
            break
    
    # Section headers patterns
    section_patterns = {
        "responsibilities": [
            r"responsibilities?",
            r"what you['\"]ll do",
            r"what you will do",
            r"key responsibilities?",
            r"duties",
            r"role and responsibilities?",
        ],
        "requirements": [
            r"requirements?",
            r"what we['\"]re looking for",
            r"what you need",
            r"must have",
            r"required",
            r"qualifications?",
        ],
        "qualifications": [
            r"qualifications?",
            r"education",
            r"experience",
            r"background",
        ],
        "benefits": [
            r"benefits?",
            r"perks?",
            r"what we offer",
            r"compensation",
            r"package",
        ],
        "skills": [
            r"skills?",
            r"technologies?",
            r"tech stack",
            r"tools",
            r"languages?",
        ],
    }
    
    # Split text into sections based on headers
    current_section = None
    section_content = []
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Check if this line is a section header
        found_section = None
        for section_name, patterns in section_patterns.items():
            for pattern in patterns:
                if re.match(rf"^({pattern})[:]?$", line_lower):
                    found_section = section_name
                    break
            if found_section:
                break
        
        if found_section:
            # Save previous section
            if current_section and section_content:
                content = "\n".join(section_content).strip()
                if current_section == "responsibilities":
                    structured["responsibilities"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
                elif current_section == "requirements":
                    structured["requirements"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
                elif current_section == "qualifications":
                    structured["qualifications"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
                elif current_section == "benefits":
                    structured["benefits"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
                elif current_section == "skills":
                    structured["skills"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
            
            current_section = found_section
            section_content = []
        else:
            if current_section:
                section_content.append(line)
            else:
                # Content before any section header goes to overview
                structured["overview"] += line + " "
    
    # Save last section
    if current_section and section_content:
        content = "\n".join(section_content).strip()
        if current_section == "responsibilities":
            structured["responsibilities"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
        elif current_section == "requirements":
            structured["requirements"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
        elif current_section == "qualifications":
            structured["qualifications"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
        elif current_section == "benefits":
            structured["benefits"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
        elif current_section == "skills":
            structured["skills"] = [item.strip() for item in content.split("\n") if item.strip() and len(item.strip()) > 10]
    
    # Clean up overview
    structured["overview"] = structured["overview"].strip()
    
    # Extract skills from text (common technologies)
    common_skills = [
        "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust", "ruby", "php",
        "react", "vue", "angular", "node.js", "django", "flask", "spring", "express",
        "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
        "git", "ci/cd", "jenkins", "github actions",
        "machine learning", "ai", "data science", "analytics",
    ]
    found_skills = []
    for skill in common_skills:
        if skill.lower() in text_lower:
            found_skills.append(skill)
    if found_skills:
        structured["skills"].extend(found_skills)
        structured["skills"] = list(set(structured["skills"]))  # Remove duplicates
    
    # Clean up empty lists and None values
    return {k: v for k, v in structured.items() if v}
