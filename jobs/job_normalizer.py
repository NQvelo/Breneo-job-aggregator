"""
Breneo job parsing + matching pipeline.

Robust normalizer that extracts derived fields from title + descriptionRaw:
workMode, seniority, roleCategory, minYearsExperience, languagesRequired,
skillsRequired, skillsPreferred, techStack, techStackCandidates.

Uses skills_catalog.json for high-precision skill extraction.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# --- Load skills catalog ---
_CATALOG_PATH = Path(__file__).parent / "data" / "skills_catalog.json"
_SKILLS_CATALOG: list[dict] = []
_SKILL_ALIAS_INDEX: dict[str, str] = {}  # alias_lower -> canonical
_SKILL_CATEGORY_INDEX: dict[str, str] = {}  # canonical -> category
_ALIAS_PATTERNS: list[tuple[str, str]] = []  # (escaped_pattern, canonical) sorted by length desc


def _load_catalog() -> None:
    global _SKILLS_CATALOG, _SKILL_ALIAS_INDEX, _SKILL_CATEGORY_INDEX, _ALIAS_PATTERNS
    if _SKILLS_CATALOG:
        return
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        _SKILLS_CATALOG = json.load(f)
    for entry in _SKILLS_CATALOG:
        canonical = entry["canonical"]
        _SKILL_CATEGORY_INDEX[canonical] = entry.get("category", "other")
        for alias in entry.get("aliases", []):
            alias_lower = alias.lower().strip()
            if alias_lower and alias_lower not in _SKILL_ALIAS_INDEX:
                _SKILL_ALIAS_INDEX[alias_lower] = canonical
    # Build patterns: (pattern, canonical), longest alias first for C vs C++ vs C#
    pattern_tuples: list[tuple[str, str, int]] = []
    for entry in _SKILLS_CATALOG:
        canonical = entry["canonical"]
        for alias in entry.get("aliases", []) + [canonical]:
            alias = alias.strip()
            if not alias:
                continue
            escaped = re.escape(alias)
            # Word boundaries; allow . after (e.g. "Go.") by not excluding it from lookahead
            # Word boundaries; don't exclude period so "Go." and "Node.js" match
            pattern = r"(?<![a-zA-Z0-9_\-])" + escaped + r"(?![a-zA-Z0-9_\-])"
            pattern_tuples.append((pattern, canonical, len(alias)))
    pattern_tuples.sort(key=lambda x: -x[2])
    _ALIAS_PATTERNS = [(p, c) for p, c, _ in pattern_tuples]


def _ensure_catalog_loaded() -> None:
    if not _SKILLS_CATALOG:
        _load_catalog()


# --- Section headings ---
_MUST_HAVE_HEADINGS = re.compile(
    r"^(?:(?:key\s+)?(?:requirements?|qualifications?|skills?)|must\s+have|required|what\s+you\s+bring|what\s+you(?:'ll|\s+will)\s+bring)\s*:?",
    re.IGNORECASE,
)
_PREFERRED_HEADINGS = re.compile(
    r"^(?:nice\s+to\s+have|preferred|plus|bonus|desired|would\s+be\s+great|helpful|optional)\s*:?",
    re.IGNORECASE,
)
_TECH_HEADINGS = re.compile(
    r"^(?:(?:tech(?:nology)?|technologies)\s+stack|tools?|our\s+stack)\s*:?",
    re.IGNORECASE,
)
_SECTION_HEADING = re.compile(
    r"^(?:[A-Z][a-z\s\-]+|[\w\s]+)\s*:?\s*$",
    re.MULTILINE,
)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """
    Split text into (section_type, body) pairs.
    section_type: "must_have" | "preferred" | "tech" | "other"
    """
    if not text or not text.strip():
        return []
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_type = "other"
    current_body: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            current_body.append(line)
            i += 1
            continue
        if _MUST_HAVE_HEADINGS.match(stripped):
            if current_body:
                sections.append((current_type, "\n".join(current_body)))
            current_type = "must_have"
            # Include content after colon on same line (e.g. "Requirements: Python, Java")
            after_colon = stripped.split(":", 1)[-1].strip() if ":" in stripped else ""
            current_body = [after_colon] if after_colon else []
        elif _PREFERRED_HEADINGS.match(stripped):
            if current_body:
                sections.append((current_type, "\n".join(current_body)))
            current_type = "preferred"
            after_colon = stripped.split(":", 1)[-1].strip() if ":" in stripped else ""
            current_body = [after_colon] if after_colon else []
        elif _TECH_HEADINGS.match(stripped):
            if current_body:
                sections.append((current_type, "\n".join(current_body)))
            current_type = "tech"
            after_colon = stripped.split(":", 1)[-1].strip() if ":" in stripped else ""
            current_body = [after_colon] if after_colon else []
        else:
            current_body.append(line)
        i += 1
    if current_body:
        sections.append((current_type, "\n".join(current_body)))
    return sections


def _extract_skills_from_text(text: str, max_skills: int = 50) -> tuple[list[str], list[str]]:
    """
    Scan text for catalog skills. Returns (canonical_skills, tech_like_candidates).
    Longest-match-first to handle C vs C++ vs C#.
    """
    _ensure_catalog_loaded()
    found: set[str] = set()
    candidates: set[str] = set()
    text_lower = text.lower()
    for pattern, canonical in _ALIAS_PATTERNS:
        if len(found) >= max_skills:
            break
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if canonical not in found:
                found.add(canonical)
    # Tech-like candidates: CamelCase, foo.js, foo-js, etc. not in catalog
    tech_token = re.compile(
        r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+|[a-z]+[A-Z][a-z]*|[\w]+\.(?:js|ts|py|jsx|tsx|css)|[\w]+-[\w]+)\b"
    )
    for m in tech_token.finditer(text):
        token = m.group(1)
        token_lower = token.lower()
        if len(token) >= 2 and token_lower not in _SKILL_ALIAS_INDEX:
            if re.match(r"^[a-zA-Z]", token) and not token.isdigit():
                candidates.add(token)
    return (sorted(found), sorted(candidates)[:20])


def extract_skills(
    text: str | None,
    title: str | None,
) -> dict[str, Any]:
    """
    Extract skills with section-aware logic.
    Returns: {required, preferred, techStack, techStackCandidates, usedFallbackSectioning}
    """
    _ensure_catalog_loaded()
    combined = ((title or "") + "\n" + (text or "")).strip()
    if not combined:
        return {
            "required": [],
            "preferred": [],
            "techStack": [],
            "techStackCandidates": [],
            "usedFallbackSectioning": True,
        }
    sections = _split_sections(combined)
    required: set[str] = set()
    preferred: set[str] = set()
    tech: set[str] = set()
    all_candidates: set[str] = set()
    used_fallback = len(sections) == 0 or all(s[0] == "other" for s in sections)
    if not sections:
        skills, candidates = _extract_skills_from_text(combined)
        required.update(skills)
        tech.update(skills)
        all_candidates.update(candidates)
    else:
        for section_type, body in sections:
            skills, candidates = _extract_skills_from_text(body)
            all_candidates.update(candidates)
            if section_type == "must_have":
                required.update(skills)
                tech.update(skills)
            elif section_type == "preferred":
                preferred.update(skills)
                tech.update(skills)
            elif section_type == "tech":
                tech.update(skills)
            else:
                required.update(skills)
                tech.update(skills)
    preferred -= required
    tech = required | preferred | tech
    # Candidates are tech-like tokens not in catalog; cap for storage
    candidates_list = sorted(all_candidates)[:25]
    return {
        "required": sorted(required),
        "preferred": sorted(preferred),
        "techStack": sorted(tech),
        "techStackCandidates": candidates_list,
        "usedFallbackSectioning": used_fallback,
    }


# --- Work mode (English only) ---
_WORK_MODE_PATTERNS = [
    (r"\bremote\b|remotely|work from home|wfh|distributed|fully remote", "remote"),
    (r"\bhybrid\b|partially remote|flex remote", "hybrid"),
    (r"\bon-?site\b|in-?office\b|onsite\b|in-person\b|office-based", "onsite"),
]


def extract_work_mode(description: str | None, title: str | None, location: str | None) -> str:
    combined = " ".join(filter(None, [title or "", description or "", location or ""])).lower()
    if not combined.strip():
        return "unknown"
    for pattern, mode in _WORK_MODE_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return mode
    return "unknown"


# --- Seniority (expanded) ---
_SENIORITY_ORDER = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4}
_SENIORITY_PATTERNS = [
    (r"\bintern\b|internship|working student", "intern"),
    (r"\bjunior\b|jr\b|entry-?level|entry level|graduate\b|associate\b(?!\s+vp)", "junior"),
    (r"\bmid-?level\b|mid\s+level|intermediate\b(?!\s+junior)", "mid"),
    (r"\bsenior\b|sr\b|advanced\b", "senior"),
    (r"\blead\b|staff\b|principal\b|head\s+of\b|director\b|vp\b", "lead"),
]


def extract_seniority(title: str | None, description: str | None) -> str:
    text = (title or "") + " " + (description or "")
    text_lower = text.lower()
    found: list[str] = []
    for pattern, level in _SENIORITY_PATTERNS:
        if re.search(pattern, text_lower):
            found.append(level)
    if not found:
        return "unknown"
    return max(found, key=lambda x: _SENIORITY_ORDER.get(x, -1))


# --- Role category inference (expanded) ---
_ROLE_TITLE_KEYWORDS = {
    "frontend": ["frontend", "front-end", "ui engineer", "web ui"],
    "backend": ["backend", "back-end", "api engineer", "server-side"],
    "fullstack": ["fullstack", "full stack", "full-stack"],
    "mobile": ["mobile", "ios", "android"],
    "data": ["data engineer", "data scientist", "ml", "machine learning", "analytics", "bi", "ai engineer"],
    "devops": ["devops", "sre", "platform engineer", "cloud engineer"],
    "qa": ["qa", "quality assurance", "test engineer", "automation engineer"],
    "security": ["security engineer", "appsec", "infosec"],
    "design": ["designer", "ui/ux", "product designer"],
    "product": ["product manager", "pm", "product owner"],
}
_ROLE_SKILL_SIGNALS = {
    "frontend": ["React", "Angular", "Vue.js", "Next.js", "Svelte", "Tailwind CSS"],
    "backend": ["Node.js", "Django", "Spring", ".NET", "Laravel", "FastAPI"],
    "mobile": ["Swift", "Kotlin", "React Native", "Flutter"],
    "data": ["Spark", "Kafka", "Airflow", "dbt", "TensorFlow", "PyTorch", "scikit-learn"],
    "devops": ["Docker", "Kubernetes", "Terraform", "CI/CD", "Prometheus"],
    "qa": ["Cypress", "Playwright", "Selenium", "JUnit", "PyTest"],
    "security": ["OWASP", "SAML", "OIDC"],
    "design": ["Figma", "Sketch", "Adobe XD"],
}


def infer_role_category(
    title: str | None,
    required_skills: list[str],
    preferred_skills: list[str],
    tech_stack: list[str],
) -> str | None:
    all_skills = set(s for s in (required_skills + preferred_skills + tech_stack) if s)
    combined_title = (title or "").lower()
    scores: dict[str, int] = {}
    for cat, keywords in _ROLE_TITLE_KEYWORDS.items():
        for kw in keywords:
            if kw in combined_title:
                scores[cat] = scores.get(cat, 0) + 2
    for cat, signals in _ROLE_SKILL_SIGNALS.items():
        for skill in signals:
            if skill in all_skills:
                scores[cat] = scores.get(cat, 0) + 3
    if "frontend" in scores and "backend" in scores:
        scores["fullstack"] = scores.get("fullstack", 0) + max(scores["frontend"], scores["backend"]) + 3
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


# --- Min years + languages (from matching_normalizer) ---
def _extract_min_years(text: str) -> int | None:
    patterns = [
        r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:experience|exp)",
        r"(\d+)\s*-\s*\d+\s*years?\s+experience",
        r"minimum\s+(\d+)\s*years",
        r"at\s+least\s+(\d+)\s*years",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            try:
                y = int(m.group(1))
                if 0 < y <= 50:
                    return y
            except (ValueError, IndexError):
                pass
    return None


def _extract_languages(description: str | None) -> list[str]:
    if not description or not description.strip():
        return []
    found: list[str] = []
    seen: set[str] = set()
    cefr = re.compile(
        r"\b(english|german|spanish|french|italian|portuguese|dutch|russian|chinese|japanese|korean|arabic)"
        r"\s*(?:level\s+)?(?:cefr\s+)?(?:at\s+)?"
        r"(native|fluent|c1|c2|b2|b1|a2|a1|proficient|business)\b",
        re.IGNORECASE,
    )
    rev = re.compile(
        r"\b(native|fluent|proficient)\s+(english|german|spanish|french|italian|portuguese|dutch|russian)\b",
        re.IGNORECASE,
    )
    simple = re.compile(
        r"\b(english|german|spanish|french|italian|portuguese|dutch|russian)\s+(?:spoken|written|required)?\b",
        re.IGNORECASE,
    )
    cefr_map = {"native": "native", "fluent": "C2", "proficient": "C1", "business": "B2", "c1": "C1", "c2": "C2", "b1": "B1", "b2": "B2", "a1": "A1", "a2": "A2"}
    for m in cefr.finditer(description):
        lang, level_raw = m.group(1).capitalize(), m.group(2).lower()
        level = cefr_map.get(level_raw, level_raw.upper() if len(level_raw) <= 2 else level_raw)
        key = f"{lang} {level}".lower()
        if key not in seen:
            seen.add(key)
            found.append(f"{lang} {level}")
    for m in rev.finditer(description):
        level_raw, lang = m.group(1).lower(), m.group(2).capitalize()
        level = cefr_map.get(level_raw, level_raw)
        key = f"{lang} {level}".lower()
        if key not in seen:
            seen.add(key)
            found.append(f"{lang} {level}")
    if not found:
        for m in simple.finditer(description):
            lang = m.group(1).capitalize()
            if lang.lower() not in seen:
                seen.add(lang.lower())
                found.append(f"{lang} (proficiency not specified)")
    return found


# --- Location country ---
def _parse_location_country(location: str | None) -> str | None:
    if not location or not location.strip():
        return None
    patterns = [
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
    ]
    loc = location.strip()
    for pattern, country in patterns:
        if re.search(pattern, loc, re.IGNORECASE):
            return country
    return None


# --- Data completeness score ---
def _compute_score(
    *,
    skills_required: list,
    seniority: str,
    work_mode: str,
    role_category: str | None,
    languages_required: list,
    min_years: int | None,
    used_fallback: bool,
) -> int:
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
    if min_years is not None:
        score += 20
    if used_fallback:
        score = max(0, score - 5)
    return min(100, score)


# --- Main normalizer ---
def normalize_job_fields(
    *,
    title: str | None = None,
    description_raw: str | None = None,
    location: str | None = None,
    qualifications_text: str | None = None,
) -> dict[str, Any]:
    """
    Produce all derived matching fields from title + descriptionRaw.
    Only regenerate when title or description_raw changed or derived fields are empty.
    Never invents values; unknown -> "unknown", missing numbers -> NULL.
    """
    desc = (description_raw or "") + "\n\n" + (qualifications_text or "")
    desc = desc.strip() or None
    combined = ((title or "") + "\n" + (desc or "")).strip()
    if not title and not desc:
        return {
            "work_mode": "unknown",
            "seniority": "unknown",
            "role_category": None,
            "min_years_experience": None,
            "skills_required": [],
            "skills_preferred": [],
            "tech_stack": [],
            "tech_stack_candidates": [],
            "languages_required": [],
            "embedding_text": None,
            "data_completeness_score": 0,
            "location_country": _parse_location_country(location),
            "used_fallback_sectioning": True,
        }
    skills_result = extract_skills(desc, title)
    work_mode = extract_work_mode(desc, title, location)
    seniority = extract_seniority(title, desc)
    role_cat = infer_role_category(
        title,
        skills_result["required"],
        skills_result["preferred"],
        skills_result["techStack"],
    )
    min_years = _extract_min_years(combined)
    languages = _extract_languages(desc)
    embedding_parts = [title or ""] + skills_result["required"] + skills_result["preferred"] + languages
    embedding_text = " ".join(filter(None, embedding_parts)).strip() or None
    score = _compute_score(
        skills_required=skills_result["required"],
        seniority=seniority,
        work_mode=work_mode,
        role_category=role_cat,
        languages_required=languages,
        min_years=min_years,
        used_fallback=skills_result["usedFallbackSectioning"],
    )
    return {
        "work_mode": work_mode,
        "seniority": seniority,
        "role_category": role_cat,
        "min_years_experience": min_years,
        "skills_required": skills_result["required"],
        "skills_preferred": skills_result["preferred"],
        "tech_stack": skills_result["techStack"],
        "tech_stack_candidates": skills_result["techStackCandidates"],
        "languages_required": languages,
        "embedding_text": embedding_text,
        "data_completeness_score": score,
        "location_country": _parse_location_country(location),
        "used_fallback_sectioning": skills_result["usedFallbackSectioning"],
    }


def get_skill_alias_index() -> dict[str, str]:
    """Return alias -> canonical mapping for fast lookup."""
    _ensure_catalog_loaded()
    return dict(_SKILL_ALIAS_INDEX)
