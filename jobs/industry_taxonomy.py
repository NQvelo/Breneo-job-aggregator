"""
Industry taxonomy and determination logic for Job.industry_tags.

Breneo job-aggregation backend: deterministic industry from company (primary) and title (disambiguation/fallback).
Implements: normalizeText, canonicalizeIndustryTag, Layer A (source) / B (company map) / C (title fallback).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

COMPANY_SUFFIXES = frozenset({"inc", "gmbh", "llc", "ltd", "ag", "plc", "co", "kg"})


def normalize_text(s: Optional[str]) -> str:
    """Lowercase, trim, collapse spaces, remove punctuation (keep letters/numbers/spaces), strip company suffixes."""
    if not s:
        return ""
    t = str(s).strip().lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    words = t.split()
    if words and words[-1] in COMPANY_SUFFIXES:
        words = words[:-1]
    return " ".join(words) if words else ""


def canonicalize_industry_tag(tag: Optional[str]) -> str:
    """normalizeText(tag) then apply INDUSTRY_SYNONYMS. Returns canonical tag or cleaned tag."""
    normalized = normalize_text(tag)
    if not normalized:
        return ""
    return INDUSTRY_SYNONYMS.get(normalized, normalized)


# ---------------------------------------------------------------------------
# INDUSTRY_SYNONYMS
# ---------------------------------------------------------------------------

INDUSTRY_SYNONYMS: Dict[str, str] = {
    "financial services": "fintech",
    "banking": "banking",
    "payments": "payments",
    "ecommerce": "e-commerce",
    "e-commerce": "e-commerce",
    "retail tech": "retail",
    "health tech": "healthcare",
    "medtech": "healthcare",
    "edtech": "education",
    "saas": "saas",
    "enterprise software": "enterprise software",
    "insurance": "insurance",
    "real estate": "real estate",
    "proptech": "real estate",
    "telecom": "telecom",
    "energy": "energy",
    "travel": "travel",
    "logistics": "logistics",
    "gaming": "gaming",
    "education": "education",
    "healthcare": "healthcare",
    "fintech": "fintech",
    "cloud": "cloud",
    "marketplace": "marketplace",
    "food delivery": "food delivery",
    "mobility": "mobility",
}

# ---------------------------------------------------------------------------
# COMPANY_INDUSTRY_MAP (normalized company key -> list of canonical tags)
# ---------------------------------------------------------------------------

COMPANY_INDUSTRY_MAP: Dict[str, List[str]] = {
    "paypal": ["fintech", "payments"],
    "stripe": ["fintech", "payments"],
    "amazon": ["e-commerce", "retail", "cloud"],
    "sap": ["enterprise software", "saas"],
    "siemens": ["industrial", "engineering"],
    "zalando": ["e-commerce", "retail"],
    "uber": ["mobility", "marketplace"],
    "delivery hero": ["food delivery", "marketplace"],
    "google": ["internet", "software", "cloud"],
    "alphabet": ["internet", "software", "cloud"],
    "meta": ["internet", "social", "software"],
    "intercom": ["saas", "customer engagement"],
    "figma": ["saas", "design"],
    "spotify": ["media", "streaming"],
    "airbnb": ["e-commerce", "travel", "marketplace"],
    "doordash": ["e-commerce", "logistics", "delivery"],
    "spacex": ["aerospace", "engineering"],
    "cloudflare": ["saas", "cloud", "infrastructure"],
    "xometry": ["e-commerce", "industrial", "manufacturing"],
    "reddit": ["media", "social"],
}

# ---------------------------------------------------------------------------
# COMPANY_ALIASES (alias -> canonical key for map lookup)
# ---------------------------------------------------------------------------

COMPANY_ALIASES: Dict[str, str] = {
    "alphabet": "google",
    "meta platforms": "meta",
}

# ---------------------------------------------------------------------------
# COMPANY_CONTEXT_RULES: multi-industry disambiguation by title keywords
# (company key -> list of (keyword_list, industry_subset))
# ---------------------------------------------------------------------------

COMPANY_CONTEXT_RULES: Dict[str, List[Tuple[List[str], List[str]]]] = {
    "amazon": [
        (["aws", "cloud", "devops", "ec2", "lambda"], ["cloud"]),
        (["e-commerce", "retail", "marketplace", "fulfillment"], ["e-commerce", "retail"]),
    ],
    "google": [
        (["cloud", "gcp", "google cloud"], ["cloud"]),
        (["ads", "advertising"], ["internet", "software"]),
    ],
}

# Default: if no title rule matches, keep all company tags (no disambiguation).

# ---------------------------------------------------------------------------
# TITLE_INDUSTRY_KEYWORDS (Layer C fallback: industry -> strong keywords)
# ---------------------------------------------------------------------------

TITLE_INDUSTRY_KEYWORDS: Dict[str, List[str]] = {
    "fintech": ["fintech", "payments", "banking", "lending", "kyc", "aml", "trading", "risk"],
    "e-commerce": ["e-commerce", "ecommerce", "checkout", "marketplace", "retail", "shopify", "storefront"],
    "healthcare": ["healthcare", "clinical", "hospital", "patient", "ehr", "medical"],
    "gaming": ["gaming", "game", "unity", "unreal"],
    "education": ["education", "edtech", "learning", "school", "student"],
    "logistics": ["logistics", "warehouse", "shipment", "fleet", "supply chain"],
    "insurance": ["insurance", "underwriting", "claims", "actuarial"],
    "telecom": ["telecom", "5g", "network operator"],
    "energy": ["energy", "oil", "gas", "renewables", "solar", "wind"],
    "real estate": ["real estate", "property", "proptech"],
    "travel": ["travel", "hotel", "airline", "booking"],
}

# Minimum key length for substring match (avoid "it", "ab")
COMPANY_SUBSTRING_MIN_KEY_LEN = 5

# Industry source labels for auditing
INDUSTRY_SOURCE_SOURCE = "source"
INDUSTRY_SOURCE_COMPANY_MAP = "company_map"
INDUSTRY_SOURCE_TITLE_FALLBACK = "title_fallback"
INDUSTRY_SOURCE_UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Layer A — Source-provided industry
# ---------------------------------------------------------------------------

def _layer_a_source(source_industry: Optional[str]) -> List[str]:
    if not source_industry:
        return []
    raw = str(source_industry).strip()
    if not raw:
        return []
    parts = re.split(r"[,/|]", raw)
    tags: List[str] = []
    for part in parts:
        canonical = canonicalize_industry_tag(part)
        if canonical and canonical not in tags:
            tags.append(canonical)
    return tags


# ---------------------------------------------------------------------------
# Layer B — Company-based industry (exact, alias, substring)
# ---------------------------------------------------------------------------

def _company_lookup_key(normalized_company: str) -> Optional[str]:
    """Return company key for COMPANY_INDUSTRY_MAP, or None."""
    if not normalized_company:
        return None
    # Exact
    if normalized_company in COMPANY_INDUSTRY_MAP:
        return normalized_company
    # Alias
    if normalized_company in COMPANY_ALIASES:
        return COMPANY_ALIASES[normalized_company]
    # Substring: keys length >= 5, sorted by length desc
    candidates = sorted(
        (k for k in COMPANY_INDUSTRY_MAP if len(k) >= COMPANY_SUBSTRING_MIN_KEY_LEN),
        key=len,
        reverse=True,
    )
    for key in candidates:
        if f" {key} " in f" {normalized_company} " or normalized_company.startswith(key + " ") or normalized_company.endswith(" " + key):
            return key
    return None


def _layer_b_company(company_name: str, job_title: str) -> Tuple[List[str], Optional[str]]:
    """Returns (tags, company_key). company_key used for disambiguation."""
    normalized = normalize_text(company_name)
    key = _company_lookup_key(normalized)
    if not key:
        return [], None
    tags = list(COMPANY_INDUSTRY_MAP.get(key, []))
    if not tags:
        return [], None
    # Disambiguation: multi-industry + title signals
    rules = COMPANY_CONTEXT_RULES.get(key, [])
    normalized_title = normalize_text(job_title)
    for keywords, subset in rules:
        if any(kw in normalized_title for kw in keywords):
            return subset, key
    return tags, key


# ---------------------------------------------------------------------------
# Layer C — Title-only inference (high confidence only)
# ---------------------------------------------------------------------------

def _layer_c_title(job_title: str) -> List[str]:
    """Infer industry from title only: >= 2 keyword hits OR title contains industry name explicitly. Tie => empty."""
    normalized_title = normalize_text(job_title)
    if not normalized_title:
        return []
    scores: Dict[str, int] = {}
    for industry, keywords in TITLE_INDUSTRY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in normalized_title)
        if count > 0:
            scores[industry] = count
    # Explicit industry name in title (treat as >= 2)
    for industry in list(scores.keys()):
        if industry in normalized_title:
            scores[industry] = max(scores.get(industry, 0), 2)
    # Accept only if >= 2 hits or explicit
    accepted = [ind for ind, score in scores.items() if score >= 2]
    if len(accepted) > 1:
        # Tie: return none unless exactly one is explicit in title
        explicit = [ind for ind in accepted if ind in normalized_title]
        if len(explicit) == 1:
            return explicit
        return []
    return accepted


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _format_industry_tags(tags: List[str]) -> str:
    """Canonicalize, dedupe, sort, join with ', '."""
    out: List[str] = []
    seen = set()
    for t in tags:
        c = canonicalize_industry_tag(t) if t else ""
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return ", ".join(sorted(out)) if out else ""


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def determine_industry_tags(
    company_name: str,
    job_title: str,
    source_industry: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Deterministic industry from (company + title). Returns (industryTagsString, industrySource).
    industrySource is one of: "source" | "company_map" | "title_fallback" | "unknown".
    """
    # Layer A
    layer_a = _layer_a_source(source_industry)
    if layer_a:
        return _format_industry_tags(layer_a), INDUSTRY_SOURCE_SOURCE

    # Layer B
    layer_b, company_key = _layer_b_company(company_name, job_title)
    if layer_b:
        return _format_industry_tags(layer_b), INDUSTRY_SOURCE_COMPANY_MAP

    # Layer C
    layer_c = _layer_c_title(job_title)
    if layer_c:
        return _format_industry_tags(layer_c), INDUSTRY_SOURCE_TITLE_FALLBACK

    return "", INDUSTRY_SOURCE_UNKNOWN


# ---------------------------------------------------------------------------
# Backward compatibility: IndustryContext + determine_industry (for fetch_jobs / backfill)
# ---------------------------------------------------------------------------

@dataclass
class IndustryContext:
    title: str
    description_raw: str
    company_name: str
    source_industry_field: Optional[str] = None


def determine_industry(ctx: IndustryContext) -> List[str]:
    """Returns list of canonical tags. Uses determine_industry_tags under the hood."""
    tags_str, _ = determine_industry_tags(
        company_name=ctx.company_name or "",
        job_title=ctx.title or "",
        source_industry=ctx.source_industry_field,
    )
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(",") if t.strip()]
