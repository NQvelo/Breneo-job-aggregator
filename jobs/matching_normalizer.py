"""
Matching fields normalizer for job-user matching system.

Populates structured fields from raw job data following safe rules:
- Unknown enums -> "unknown"
- Unknown numbers -> NULL
- Empty arrays -> []
- Never invent values

Each field is populated separately (no single-text-field matching).
"""

from __future__ import annotations

import re
from typing import Any

# --- Work mode detection ---
_WORK_MODE_PATTERNS = [
    (r"\bremote\b|work from home|wfh|distributed|fully remote", "remote"),
    (r"\bhybrid\b|partially remote|flex remote", "hybrid"),
    (r"\bon-?site\b|in-?office\b|onsite\b|in-person\b|office-based", "onsite"),
]


def extract_work_mode(description: str | None, title: str | None, location: str | None) -> str:
    """Detect work mode from description/title/location. Returns 'unknown' if not detected."""
    combined = " ".join(
        filter(None, [title or "", description or "", location or ""])
    ).lower()
    if not combined.strip():
        return "unknown"
    for pattern, mode in _WORK_MODE_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return mode
    return "unknown"


# --- Seniority detection ---
_SENIORITY_PATTERNS = [
    (r"\bintern\b|internship", "intern"),
    (r"\bjunior\b|jr\b|entry-?level|graduate\b|associate\b(?!\s+vp)", "junior"),
    (r"\blead\b|principal\b|staff\b|director\b|vp\b|head of\b", "lead"),
    (r"\bsenior\b|sr\b|experienced\b(?!\s+junior)", "senior"),
    (r"\bmid-?level\b|mid\b|mid-level", "mid"),
]


def extract_seniority(title: str | None, description: str | None) -> str:
    """Detect seniority from title then description. Returns 'unknown' if unclear."""
    # Prefer title (more reliable)
    text = (title or "") + " " + (description or "")
    text_lower = text.lower()
    for pattern, level in _SENIORITY_PATTERNS:
        if re.search(pattern, text_lower):
            return level
    return "unknown"


# --- Role category inference ---
_ROLE_CATEGORY_KEYWORDS = {
    "frontend": ["frontend", "front-end", "react", "vue", "angular", "ui/ux", "web ui"],
    "backend": ["backend", "back-end", "api", "server", "microservices", "java", "go", "golang"],
    "data": ["data engineer", "data scientist", "analytics", "ml", "machine learning", "etl", "bigquery"],
    "fullstack": ["fullstack", "full-stack", "full stack"],
    "devops": ["devops", "sre", "infrastructure", "kubernetes", "terraform"],
    "mobile": ["mobile", "ios", "android", "react native", "flutter"],
}


def infer_role_category(title: str | None, skills: list[str]) -> str | None:
    """Infer role category from title + skills. Returns None if unclear."""
    combined = " ".join([title or ""] + skills).lower()
    if not combined.strip():
        return None
    scores: dict[str, int] = {}
    for cat, keywords in _ROLE_CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                scores[cat] = scores.get(cat, 0) + 1
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


# --- Skills required vs preferred ---
# Tech skills catalog (subset from job_posting_parser)
_SKILLS_KEYWORDS = frozenset([
    "python", "javascript", "java", "typescript", "go", "golang", "rust", "c++", "c#",
    "ruby", "swift", "kotlin", "php", "scala", "r", "sql", "html", "css", "solidity",
    "react", "angular", "vue", "node.js", "nodejs", "django", "flask", "fastapi",
    "spring", "spring boot", ".net", "rails", "express", "next.js", "svelte",
    "redux", "graphql", "rest api", "restful", "aws", "gcp", "azure", "docker",
    "kubernetes", "k8s", "terraform", "ansible", "jenkins", "ci/cd", "github actions",
    "linux", "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
    "dynamodb", "bigquery", "snowflake", "git", "agile", "scrum", "machine learning",
    "ml", "data science", "api", "microservices", "tdd", "test driven development",
])

_PREFERRED_SECTION_PATTERNS = [
    r"nice to have\b", r"preferred\b", r"bonus\b", r"plus\b", r"desired\b",
    r"would be great\b", r"helpful\b", r"optional\b",
]


def _extract_skills_from_text(text: str, max_skills: int = 20) -> list[str]:
    """Extract skill keywords from text, preserving casing from first occurrence."""
    if not text or not text.strip():
        return []
    text_lower = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    for skill in sorted(_SKILLS_KEYWORDS, key=len, reverse=True):
        if len(found) >= max_skills:
            break
        if skill in seen:
            continue
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text_lower):
            seen.add(skill)
            m = re.search(pattern, text, re.IGNORECASE)
            found.append(m.group(0) if m else skill.title())
    return found


def extract_skills_required_preferred(
    description: str | None,
    qualifications_text: str | None,
) -> tuple[list[str], list[str]]:
    """
    Split skills into required vs preferred based on section headings.
    If no explicit preferred section, put all detected skills into required.
    """
    if not description and not qualifications_text:
        return [], []
    text = (description or "") + "\n\n" + (qualifications_text or "")
    text_lower = text.lower()

    # Find preferred section (text after "nice to have", "preferred", etc.)
    preferred_text = ""
    for pattern in _PREFERRED_SECTION_PATTERNS:
        m = re.search(pattern, text_lower, re.IGNORECASE)
        if m:
            idx = m.end()
            # Take next ~500 chars or until next major section
            chunk = text[idx : idx + 600]
            preferred_text += " " + chunk
            break

    preferred_skills = _extract_skills_from_text(preferred_text, max_skills=15)
    all_skills = _extract_skills_from_text(text)
    required_skills = [s for s in all_skills if s.lower() not in {x.lower() for x in preferred_skills}]
    return required_skills, preferred_skills


def extract_tech_stack(title: str | None, description: str | None, skills: list[str]) -> list[str]:
    """Tech stack = skills + tech mentioned in title. Deduplicated."""
    combined = " ".join([title or "", description or ""] + skills).lower()
    return list(dict.fromkeys(_extract_skills_from_text(combined, max_skills=25)))


# --- Languages with CEFR ---
_LANGUAGE_CEFR_PATTERN = re.compile(
    r"\b(english|german|spanish|french|italian|portuguese|dutch|russian|chinese|japanese|korean|arabic)"
    r"\s*(?:level\s+)?(?:cefr\s+)?(?:at\s+)?"
    r"(native|fluent|c1|c2|b2|b1|a2|a1|proficient|business)\b",
    re.IGNORECASE,
)
_LANGUAGE_REVERSE_PATTERN = re.compile(
    r"\b(native|fluent|proficient)\s+(english|german|spanish|french|italian|portuguese|dutch|russian)\b",
    re.IGNORECASE,
)
_LANGUAGE_SIMPLE_PATTERN = re.compile(
    r"\b(english|german|spanish|french|italian|portuguese|dutch|russian)\s+(?:spoken|written|required)?\b",
    re.IGNORECASE,
)
_CEFR_MAP = {
    "native": "native", "fluent": "C2", "proficient": "C1", "business": "B2",
    "c1": "C1", "c2": "C2", "b1": "B1", "b2": "B2", "a1": "A1", "a2": "A2",
}


def extract_languages_required(description: str | None) -> list[str]:
    """Extract languages with CEFR level. Format: 'English C1', 'German native', etc."""
    if not description or not description.strip():
        return []
    found: list[str] = []
    seen: set[str] = set()
    for m in _LANGUAGE_CEFR_PATTERN.finditer(description):
        lang = m.group(1).capitalize()
        level_raw = m.group(2).lower()
        level = _CEFR_MAP.get(level_raw, level_raw.upper() if len(level_raw) <= 2 else level_raw)
        key = f"{lang} {level}".lower()
        if key not in seen:
            seen.add(key)
            found.append(f"{lang} {level}")
    for m in _LANGUAGE_REVERSE_PATTERN.finditer(description):
        level_raw = m.group(1).lower()
        lang = m.group(2).capitalize()
        level = _CEFR_MAP.get(level_raw, level_raw)
        key = f"{lang} {level}".lower()
        if key not in seen:
            seen.add(key)
            found.append(f"{lang} {level}")
    if not found:
        for m in _LANGUAGE_SIMPLE_PATTERN.finditer(description):
            lang = m.group(1).capitalize()
            if lang.lower() not in seen:
                seen.add(lang.lower())
                found.append(f"{lang} (proficiency not specified)")
    return found


# --- Legal / constraints ---
def extract_visa_sponsorship(description: str | None) -> str:
    """Detect visa sponsorship. Returns 'unknown' if not mentioned."""
    if not description:
        return "unknown"
    d = description.lower()
    if re.search(r"visa\s+sponsorship|sponsor\s+visa|h-?1b\s+sponsor", d):
        if re.search(r"(?:do|does)\s+not\s+sponsor|no\s+sponsorship|cannot\s+sponsor", d):
            return "no"
        return "yes"
    return "unknown"


def extract_work_authorization_required(description: str | None) -> str:
    """Detect work authorization requirement."""
    if not description:
        return "unknown"
    d = description.lower()
    if re.search(r"work\s+authorization|authorized\s+to\s+work|work\s+permit", d):
        if re.search(r"must\s+have|required|eligible", d):
            return "yes"
        return "yes"  # Mentioning it usually means required
    return "unknown"


# --- Min years experience ---
_MIN_YEARS_PATTERNS = [
    r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:experience|exp)",
    r"(\d+)\s*-\s*\d+\s*years?\s+experience",
    r"minimum\s+(\d+)\s*years",
    r"at\s+least\s+(\d+)\s*years",
]


def extract_min_years_experience(description: str | None, title: str | None) -> int | None:
    """Extract min years of experience. Returns None if unknown (never 0)."""
    text = (title or "") + " " + (description or "")
    if not text.strip():
        return None
    for pattern in _MIN_YEARS_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                y = int(m.group(1))
                if 0 < y <= 50:
                    return y
            except (ValueError, IndexError):
                pass
    return None


# --- Location country ---
_COUNTRY_PATTERNS = [
    (r"\b(usa|united states|u\.s\.?|us\b)\b", "USA"),
    (r"\b(uk|united kingdom|u\.k\.?|great britain)\b", "United Kingdom"),
    (r"\b(germany|deutschland)\b", "Germany"),
    (r"\b(france)\b", "France"),
    (r"\b(netherlands|holland)\b", "Netherlands"),
    (r"\b(canada)\b", "Canada"),
    (r"\b(australia)\b", "Australia"),
    (r"\b(ireland)\b", "Ireland"),
    (r"\b(spain|spaña)\b", "Spain"),
    (r"\b(poland)\b", "Poland"),
    (r"\b(georgia)\b", "Georgia"),
    (r"\b(remote)\b", None),  # Skip "remote" as country
]


def parse_location_country(location: str | None) -> str | None:
    """Parse country from location string. Returns None if not found."""
    if not location or not location.strip():
        return None
    loc = location.strip()
    for pattern, country in _COUNTRY_PATTERNS:
        if country and re.search(pattern, loc, re.IGNORECASE):
            return country
    tail = loc.rsplit(",", 1)[-1].strip() if "," in loc else loc
    if re.fullmatch(r"(?i)england|scotland|wales|northern ireland", tail):
        return "United Kingdom"
    return None


# --- Embedding text ---
def build_embedding_text(
    title: str | None,
    skills_required: list[str],
    skills_preferred: list[str],
    languages_required: list[str],
) -> str | None:
    """Build text for embedding: title + skills + languages. Returns None if empty."""
    parts = []
    if title and title.strip():
        parts.append(title.strip())
    if skills_required:
        parts.append(" ".join(skills_required))
    if skills_preferred:
        parts.append(" ".join(skills_preferred))
    if languages_required:
        parts.append(" ".join(languages_required))
    text = " ".join(parts).strip()
    return text if text else None


# --- Data completeness score ---
def compute_data_completeness_score(
    *,
    skills_required: list[str],
    seniority: str,
    work_mode: str,
    role_category: str | None,
    languages_required: list[str],
    embedding_vector: Any,
    min_years_experience: int | None,
) -> int:
    """Compute 0-100 completeness score. Clamp to max 100."""
    score = 0
    if skills_required:
        score += 20
    if seniority != "unknown":
        score += 10
    if work_mode != "unknown":
        score += 10
    if role_category:
        score += 10
    if languages_required:
        score += 10
    if embedding_vector is not None and embedding_vector:
        score += 20
    if min_years_experience is not None:
        score += 20
    return min(100, score)


# --- Main normalizer ---
def normalize_matching_fields(
    *,
    title: str | None = None,
    description: str | None = None,
    location: str | None = None,
    qualifications_text: str | None = None,
    skills_required_existing: list[str] | None = None,
) -> dict[str, Any]:
    """
    Produce normalized matching fields from raw job data.
    Use for both insert and update. Never invents values.
    """
    skills_req, skills_pref = extract_skills_required_preferred(description, qualifications_text)
    if skills_required_existing and not skills_req:
        skills_req = skills_required_existing
    tech_stack = extract_tech_stack(title, description, skills_req + skills_pref)
    languages = extract_languages_required(description)
    embedding_text = build_embedding_text(title, skills_req, skills_pref, languages)
    min_years = extract_min_years_experience(description, title)

    # embedding_vector: generate only if embedding_text exists (placeholder - no external API)
    embedding_vector = None  # Set by embedding service when available

    score = compute_data_completeness_score(
        skills_required=skills_req,
        seniority=extract_seniority(title, description),
        work_mode=extract_work_mode(description, title, location),
        role_category=infer_role_category(title, skills_req + skills_pref),
        languages_required=languages,
        embedding_vector=embedding_vector,
        min_years_experience=min_years,
    )

    return {
        "work_mode": extract_work_mode(description, title, location),
        "seniority": extract_seniority(title, description),
        "role_category": infer_role_category(title, skills_req + skills_pref),
        "min_years_experience": min_years,
        "skills_required": skills_req,
        "skills_preferred": skills_pref,
        "tech_stack": tech_stack,
        "languages_required": languages,
        "visa_sponsorship": extract_visa_sponsorship(description),
        "work_authorization_required": extract_work_authorization_required(description),
        "embedding_text": embedding_text,
        "embedding_vector": embedding_vector,
        "data_completeness_score": score,
        "location_country": parse_location_country(location),
    }
