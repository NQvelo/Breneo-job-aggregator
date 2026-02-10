"""
Industry taxonomy and determination logic for Job.industry_tags.

This module implements:
- INDUSTRY_SYNONYMS
- COMPANY_INDUSTRY_MAP
- KEYWORD_INDUSTRY_MAP
- determine_industry() helper
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
import re


# ---------------------------------------------------------------------------
# 1) Synonym normalization
# ---------------------------------------------------------------------------

INDUSTRY_SYNONYMS: Dict[str, str] = {
    "financial services": "fintech",
    "banking": "banking",
    "payments": "payments",
    "ecommerce": "e-commerce",
    "retail tech": "retail",
    "health tech": "healthcare",
    "medtech": "healthcare",
    "edtech": "education",
    "saas": "saas",
    "enterprise software": "enterprise software",
}


# ---------------------------------------------------------------------------
# 2) Company → industries
# ---------------------------------------------------------------------------

COMPANY_INDUSTRY_MAP: Dict[str, List[str]] = {
    "paypal": ["fintech", "payments"],
    "stripe": ["fintech", "payments"],
    "amazon": ["e-commerce", "retail", "cloud"],
    "sap": ["enterprise software", "saas"],
    "siemens": ["industrial", "engineering"],
    "zalando": ["e-commerce", "retail"],
    # From fetch_jobs COMPANIES list
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
# 3) Keyword → industries
# ---------------------------------------------------------------------------

KEYWORD_INDUSTRY_MAP: Dict[str, List[str]] = {
    "fintech": ["payment", "bank", "card", "lending", "kyc", "aml", "trading"],
    "e-commerce": ["checkout", "cart", "order", "storefront", "marketplace", "shop"],
    "healthcare": ["patient", "clinical", "hospital", "ehr", "medical"],
    "gaming": ["game", "unity", "unreal", "multiplayer", "gaming"],
    "education": ["student", "learning", "edtech", "course", "academy"],
    "logistics": ["delivery", "warehouse", "fleet", "logistics", "shipment"],
}


@dataclass
class IndustryContext:
    title: str
    description_raw: str
    company_name: str
    source_industry_field: Optional[str] = None


def _clean_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _normalize_company_name(name: str) -> str:
    name = _clean_text(name)
    # Remove punctuation so "PayPal, Inc." → "paypal inc"
    return re.sub(r"[^\w\s]", "", name)


def _normalize_industry_token(raw: str) -> str:
    token = _clean_text(raw)
    if not token:
        return ""
    # Try full string first
    if token in INDUSTRY_SYNONYMS:
        return INDUSTRY_SYNONYMS[token]
    # No synonym; keep cleaned token as-is
    return token


def _from_source_industry(ctx: IndustryContext) -> List[str]:
    if not ctx.source_industry_field:
        return []

    raw = str(ctx.source_industry_field).strip() if ctx.source_industry_field else ""
    if not raw:
        return []
    # Many APIs provide comma-separated industries/categories
    parts: Iterable[str] = re.split(r"[,/]", raw)
    normalized: List[str] = []
    for part in parts:
        token = _normalize_industry_token(part)
        if token:
            normalized.append(token)
    # Deduplicate while preserving order
    seen = set()
    result: List[str] = []
    for t in normalized:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _from_company(ctx: IndustryContext) -> List[str]:
    company_key = _normalize_company_name(ctx.company_name)
    if not company_key:
        return []
    # Exact match first (e.g. "stripe")
    tags = COMPANY_INDUSTRY_MAP.get(company_key, [])
    if tags:
        return tags
    # Fallback: match by first word so "stripe inc" / "stripe" both match
    first_word = company_key.split()[0] if company_key.split() else ""
    return COMPANY_INDUSTRY_MAP.get(first_word, [])


def _from_keywords(ctx: IndustryContext) -> List[str]:
    title = _clean_text(ctx.title)
    blob = f"{ctx.title}\n{ctx.description_raw}"
    blob = _clean_text(blob)
    if not blob and not title:
        return []

    matched: List[str] = []
    for industry, keywords in KEYWORD_INDUSTRY_MAP.items():
        count = 0
        for kw in keywords:
            if kw in blob:
                count += 1
        # High-confidence rule
        if count >= 2 or (industry in title):
            matched.append(industry)

    # Deduplicate
    seen = set()
    result: List[str] = []
    for t in matched:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def determine_industry(ctx: IndustryContext) -> List[str]:
    """
    Determine canonical industry tags for a job.

    Priority:
    1) source-provided industry/category/sector (via INDUSTRY_SYNONYMS)
    2) COMPANY_INDUSTRY_MAP
    3) KEYWORD_INDUSTRY_MAP (high-confidence only)
    """
    # Step 1: source-provided
    tags = _from_source_industry(ctx)
    if tags:
        return _format_tags(tags)

    # Step 2: company map
    tags = _from_company(ctx)
    if tags:
        return _format_tags(tags)

    # Step 3: keyword inference
    tags = _from_keywords(ctx)
    if tags:
        return _format_tags(tags)

    return []


def _format_tags(tags: Iterable[str]) -> List[str]:
    cleaned = [_clean_text(t) for t in tags if _clean_text(t)]
    unique_sorted = sorted(set(cleaned))
    return unique_sorted

