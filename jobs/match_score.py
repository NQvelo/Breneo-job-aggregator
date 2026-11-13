"""
Job match score. One integer, 0–100, for a list row and for a single job.

Ported from breneoapp:
- src/utils/displayedJobMatch.ts (`matchJobAsShownOnJobPost`)
- src/services/matching.ts (`matchJobToUser`, `computeExpLevelMatch`, language gate)
- src/services/industry/computeIndustryMatch.ts
- src/services/industry/industry_taxonomy.ts (`INDUSTRY_SYNONYMS`, `INDUSTRY_RELATED`, `parseIndustryTags`)

Skill percent is required-skill coverage only. Preferred skills and tech stack
are ignored. A null ring is returned as null and counted as 0 in the overall
number, which is what the app does when it passes `percent ?? 0`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .skill_variants import normalize_skill_list

SENIORITY_LEVELS = ("intern", "junior", "mid", "senior", "lead")
SENIORITY_RANK = {level: index for index, level in enumerate(SENIORITY_LEVELS)}
USER_SENIORITY = SENIORITY_RANK.keys() | {"unknown"}

_SENIORITY_PATTERNS = (
    (re.compile(r"\bintern\b", re.IGNORECASE), "intern"),
    (re.compile(r"\bjunior\b|\bentry\b", re.IGNORECASE), "junior"),
    (re.compile(r"\bmid\b|\bmiddle\b|\bintermediate\b", re.IGNORECASE), "mid"),
    (re.compile(r"\bsenior\b", re.IGNORECASE), "senior"),
    (re.compile(r"\blead\b|\bprincipal\b|\bstaff\b", re.IGNORECASE), "lead"),
)

# variant → canonical lowercase industry tag
INDUSTRY_SYNONYMS = {
    "financial services": "fintech",
    "finance": "fintech",
    "fs": "fintech",
    "banking": "banking",
    "payments": "payments",
    "e commerce": "e-commerce",
    "ecommerce": "e-commerce",
    "retail": "retail",
    "insurance": "insurance",
    "enterprise software": "enterprise software",
    "saas": "saas",
    "software as a service": "saas",
    "medtech": "medtech",
    "medical technology": "medtech",
    "pharma": "pharma",
    "pharmaceutical": "pharma",
    "healthcare": "healthcare",
    "health care": "healthcare",
    "marketplace": "marketplace",
    "market place": "marketplace",
    "technology": "technology",
    "tech": "technology",
    "software": "technology",
    "cloud": "cloud",
    "cloud computing": "cloud",
    "design": "design",
    "ui/ux": "design",
    "marketing": "marketing",
    "sales": "sales",
    "hr": "hr",
    "human resources": "hr",
    "customer service": "customer service",
    "consulting": "consulting",
    "content": "content",
}

INDUSTRY_RELATED = {
    "fintech": ["banking", "insurance", "payments"],
    "banking": ["fintech", "payments"],
    "payments": ["fintech", "banking"],
    "e-commerce": ["retail", "marketplace"],
    "retail": ["e-commerce", "marketplace"],
    "marketplace": ["e-commerce", "retail"],
    "healthcare": ["medtech", "pharma"],
    "medtech": ["healthcare", "pharma"],
    "pharma": ["healthcare", "medtech"],
    "technology": ["saas", "cloud", "design"],
    "saas": ["technology", "enterprise software"],
    "enterprise software": ["saas", "technology"],
    "cloud": ["technology"],
    "design": ["technology", "content"],
    "marketing": ["sales", "content"],
    "sales": ["marketing"],
    "content": ["design", "marketing"],
}

_CEFR_ORDER = ["a1", "a2", "b1", "b2", "c1", "c2", "native"]
_LANGUAGE_RE = re.compile(r"^(.+?)\s+(a1|a2|b1|b2|c1|c2|native)$", re.IGNORECASE)
_INDUSTRY_SPACE_RE = re.compile(r"\s+")


def js_round(value: float) -> int:
    """Math.round: halves go toward +infinity. Not Python's bankers' round."""
    if math.isnan(value):
        return 0
    return math.floor(value + 0.5)


def parse_seniority(raw) -> str | None:
    """matching.ts `parseSeniority`. Exact level, then title words, else null."""
    if not isinstance(raw, str):
        return None
    value = raw.lower().strip()
    if not value:
        return None
    if value in SENIORITY_RANK:
        return value
    for pattern, level in _SENIORITY_PATTERNS:
        if pattern.search(value):
            return level
    return None


def resolve_seniority(field_value, title) -> str | None:
    """Stored seniority: the job field when it is a level, otherwise the title."""
    return parse_seniority(field_value) or parse_seniority(title)


@dataclass(frozen=True)
class UserSnapshot:
    user_id: str
    profile_version: str
    skills: list[str]
    seniority: str
    years_experience_total: float | None
    industry_years: dict[str, float]
    languages: list[str]


@dataclass(frozen=True)
class MatchScore:
    match_percent: int
    skills_percent: int | None
    experience_percent: int | None
    industry_percent: int | None


class SnapshotError(ValueError):
    pass


def _optional_number(value, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SnapshotError(f"{field} must be a number or null")
    return float(value)


def _string_list(value, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SnapshotError(f"{field} must be a list of strings")
    return value


def parse_snapshot(payload: dict) -> UserSnapshot:
    if not isinstance(payload, dict):
        raise SnapshotError("snapshot must be an object")
    user_id = payload.get("userId", payload.get("user_id"))
    profile_version = payload.get("profileVersion", payload.get("profile_version"))
    if not isinstance(user_id, str) or not user_id.strip():
        raise SnapshotError("userId is required")
    if not isinstance(profile_version, str) or not profile_version.strip():
        raise SnapshotError("profileVersion is required")

    seniority_raw = payload.get("seniority", "unknown")
    if not isinstance(seniority_raw, str):
        raise SnapshotError("seniority must be a string")
    seniority = seniority_raw.lower().strip()
    if seniority not in USER_SENIORITY:
        raise SnapshotError("seniority must be intern, junior, mid, senior, lead, or unknown")

    years_key = "yearsExperienceTotal" if "yearsExperienceTotal" in payload else "years_experience_total"
    industry_key = "industryYears" if "industryYears" in payload else "industry_years"
    industry_raw = payload.get(industry_key, {})
    if industry_raw is None:
        industry_raw = {}
    if not isinstance(industry_raw, dict):
        raise SnapshotError("industryYears must be an object")
    industry_years: dict[str, float] = {}
    for tag, years in industry_raw.items():
        if not isinstance(tag, str):
            raise SnapshotError("industryYears keys must be strings")
        if isinstance(years, bool) or not isinstance(years, (int, float)):
            raise SnapshotError("industryYears values must be numbers")
        if years <= 0:
            continue
        key = tag.strip().lower()
        if not key:
            continue
        industry_years[key] = industry_years.get(key, 0.0) + float(years)

    return UserSnapshot(
        user_id=user_id.strip(),
        profile_version=profile_version.strip(),
        skills=normalize_skill_list(_string_list(payload.get("skills", []), "skills")),
        seniority=seniority,
        years_experience_total=_optional_number(payload.get(years_key), "yearsExperienceTotal"),
        industry_years=industry_years,
        languages=_string_list(payload.get("languages", []), "languages"),
    )


def _skills_percent(required: list[str], user_skills: list[str]) -> int | None:
    if not required:
        return None
    user_set = set(user_skills)
    matched = sum(1 for skill in required if skill in user_set)
    return js_round(100 * matched / len(required))


def _experience_percent(
    job_seniority: str | None,
    user_seniority: str,
    job_years: float | None,
    user_years: float | None,
) -> int | None:
    seniority_component = None
    job_rank = SENIORITY_RANK.get(job_seniority) if job_seniority else None
    user_rank = SENIORITY_RANK.get(user_seniority) if user_seniority != "unknown" else None
    if job_rank is not None:
        if user_rank is None:
            seniority_component = 0.5
        else:
            diff = user_rank - job_rank
            if diff == 0:
                seniority_component = 1.0
            elif diff == 1:
                seniority_component = 0.85
            elif diff >= 2:
                seniority_component = 0.75
            elif diff == -1:
                seniority_component = 0.55
            else:
                seniority_component = 0.25

    years_component = None
    if job_years is not None and user_years is not None:
        if user_years >= job_years:
            years_component = 1.0
        elif job_years == 0:
            years_component = 0.0
        else:
            years_component = min(1.0, max(0.0, user_years / job_years))

    parts: list[tuple[float, float]] = []
    if seniority_component is not None:
        parts.append((0.6, seniority_component))
    if years_component is not None:
        parts.append((0.4, years_component))
    if not parts:
        return None
    total_w = sum(weight for weight, _ in parts)
    return js_round(sum(weight * value for weight, value in parts) / total_w * 100)


def parse_industry_tags(tags_string) -> list[str]:
    """parseIndustryTags: split, trim, lowercase, collapse spaces, synonyms, dedupe."""
    if not isinstance(tags_string, str):
        return []
    raw = tags_string.strip()
    if not raw:
        return []
    tags = [
        _INDUSTRY_SPACE_RE.sub(" ", piece.strip().lower())
        for piece in raw.split(",")
    ]
    tags = [tag for tag in tags if tag]
    canonical = [INDUSTRY_SYNONYMS.get(tag, tag) for tag in tags]
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in canonical:
        if tag and tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def compute_industry_percent(job_tags: list[str], user_years: dict[str, float]) -> int | None:
    """computeIndustryMatch percent. No tags → null. Tags and no years → 0."""
    tags = [tag for tag in job_tags if tag]
    if not tags:
        return None
    total = 0.0
    for tag in tags:
        key = tag.strip().lower()
        years = user_years.get(key)
        if years is not None and years > 0:
            base = 1.0
        else:
            related = INDUSTRY_RELATED.get(key, [])
            found = next((item for item in related if user_years.get(item, 0) > 0), None)
            if found:
                base = 0.5
                years = user_years[found]
            else:
                base = 0.0
                years = 0.0
        years_boost = _clamp(years / 5, 0, 1) * 0.2
        total += _clamp(base + years_boost, 0, 1.0)
    return js_round((total / len(tags)) * 100)


def _industry_percent(industry_tags, user_years: dict[str, float]) -> int | None:
    if isinstance(industry_tags, list):
        if not any(isinstance(tag, str) and tag.strip() for tag in industry_tags):
            return None
        text = ",".join(tag for tag in industry_tags if isinstance(tag, str))
    elif isinstance(industry_tags, str):
        if not industry_tags.strip():
            return None
        text = industry_tags
    else:
        return None
    canonical = parse_industry_tags(text)
    if not canonical:
        return None
    return compute_industry_percent(canonical, user_years)


def _cefr_index(level: str) -> int:
    try:
        return _CEFR_ORDER.index(level)
    except ValueError:
        return -1


def _parse_language_level(value: str) -> tuple[str, str]:
    text = value.strip()
    match = _LANGUAGE_RE.match(text)
    if match:
        return match.group(1).strip().lower(), match.group(2).lower()
    return text.lower(), "native"


def _language_missing(required, user_languages: list[str]) -> bool:
    if not isinstance(required, list) or not required:
        return False
    best: dict[str, str] = {}
    for raw in user_languages:
        if not isinstance(raw, str) or not raw.strip():
            continue
        lang, level = _parse_language_level(raw)
        existing = best.get(lang)
        if existing is None or _cefr_index(level) > _cefr_index(existing):
            best[lang] = level
    for raw in required:
        if not isinstance(raw, str) or not raw.strip():
            continue
        lang, level = _parse_language_level(raw)
        user_level = best.get(lang)
        required_index = _cefr_index(level)
        if required_index == -1:
            continue
        if user_level is None or _cefr_index(user_level) < required_index:
            return True
    return False


def _job_years(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def score_job(job, snapshot: UserSnapshot) -> MatchScore:
    """Score one job from its stored match card. Does not read the description."""
    skills = _skills_percent(normalize_skill_list(getattr(job, "skills_required", None)), snapshot.skills)
    experience = _experience_percent(
        parse_seniority(getattr(job, "seniority", None)),
        snapshot.seniority,
        _job_years(getattr(job, "min_years_experience", None)),
        snapshot.years_experience_total,
    )
    industry = _industry_percent(getattr(job, "industry_tags", None), snapshot.industry_years)
    overall = (0.5 * (skills or 0) / 100) + (0.3 * (experience or 0) / 100) + (0.2 * (industry or 0) / 100)
    overall *= 100
    if _language_missing(getattr(job, "languages_required", None), snapshot.languages):
        overall *= 0.75
    overall = max(0.0, min(100.0, overall))
    return MatchScore(
        match_percent=js_round(overall),
        skills_percent=skills,
        experience_percent=experience,
        industry_percent=industry,
    )
