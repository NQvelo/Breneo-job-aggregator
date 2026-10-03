"""
Decide whether an ATS listing is truly worldwide remote.

Breneo only keeps jobs where a candidate from *any* country can apply.

Important: location="Remote" is NOT enough. Many postings say Remote but still
restrict hiring to a country, region, city, or work-authorization zone. This
filter requires positive worldwide/open-anywhere signals and rejects geo locks
found in the location line, structured eligibility fields, or description.
"""

from __future__ import annotations

import re
from typing import Any

# --- Remote workplace ---
_REMOTE_WORD = re.compile(
    r"\b("
    r"remote|wfh|work[\s\-]?from[\s\-]?home|work[\s\-]?from[\s\-]?anywhere|"
    r"distributed|fully[\s\-]?remote|100%\s*remote|telecommute"
    r")\b",
    re.I,
)
_HYBRID_OR_OFFICE = re.compile(
    r"\b("
    r"hybrid|on[\s\-]?site|in[\s\-]?office|office[\s\-]?based|in[\s\-]?person|"
    r"must\s+come\s+to\s+(?:the\s+)?office|days?\s+per\s+week\s+in\s+(?:the\s+)?office"
    r")\b",
    re.I,
)

# --- Positive: open to applicants anywhere ---
_WORLDWIDE_POSITIVE = re.compile(
    r"(?i)"
    r"(?:"
    r"\bworldwide\b|\bworld[\s\-]?wide\b|\bglobally\b|"
    r"\bglobal\s+remote\b|\bremote\s+global\b|"
    r"remote\s*[(/\-–—]\s*global|\bglobal\s*[)/\-–—]\s*remote|"
    r"\bwork\s+from\s+anywhere\b|\banywhere\s+in\s+the\s+world\b|"
    r"\bfrom\s+anywhere\b|\bhire\s+globally\b|\bhiring\s+globally\b|"
    r"\bfully\s+distributed\b|\bdistributed\s+(?:team|company|workforce)\b|"
    r"\bremote[\s\-]?first\b|\ball\s+time\s+zones\b|\bany\s+time\s+zone\b|"
    r"\bno\s+geographic\s+restrictions?\b|\bno\s+location\s+restrictions?\b|"
    r"\bopen\s+to\s+(?:candidates|applicants)\s+(?:from\s+)?anywhere\b|"
    r"\bcandidates?\s+from\s+any\s+country\b|\bapplicants?\s+from\s+any\s+country\b|"
    r"\binternational(?:ly)?\s+remote\b|\bremote\s+international\b"
    r")"
)

_GEO_TOKEN = (
    r"(?:"
    r"united\s+states|u\.s\.a?\.?|\busa\b|(?<![a-z])us(?![a-z])|"
    r"america(?!\s+latina)|north\s+america|latam|latin\s+america|"
    r"united\s+kingdom|u\.k\.|\buk\b|england|scotland|wales|great\s+britain|"
    r"canada|germany|france|spain|italy|india|brazil|mexico|japan|china|"
    r"australia|new\s+zealand|netherlands|belgium|austria|switzerland|"
    r"sweden|norway|denmark|finland|poland|portugal|israel|singapore|"
    r"south\s+korea|hong\s+kong|ireland|philippines|pakistan|nigeria|"
    r"ukraine|romania|argentina|chile|colombia|uruguay|peru|ecuador|"
    r"emea|apac|eea\b|(?<![a-z])eu(?![a-z])|europe|"
    r"california|texas|florida|new\s+york|colorado|illinois|washington|"
    r"san\s+francisco|seattle|austin|boston|london|berlin|toronto|"
    r"amsterdam|dublin|sydney|bangalore|bengaluru|stockholm|buenos\s+aires|"
    r"montevideo|mexico\s+city|são\s+paulo|sao\s+paulo"
    r")"
)

_REGION_LOCKED_LOCATION = re.compile(
    rf"(?i)"
    rf"(?:"
    rf"remote\s*"
    rf"(?:[,;|/()\[\]:\-–—]|\s+in\s+|\s+from\s+|\s+for\s+|\s+within\s+|\s+across\s+)"
    rf".{{0,80}}?{_GEO_TOKEN}"
    rf"|"
    rf"{_GEO_TOKEN}.{{0,40}}?\bremote\b"
    rf"|"
    rf"\b(?:only|exclusively)\s+(?:in|within|for)\s+{_GEO_TOKEN}"
    rf")"
)

_GEO_LOCK_IN_TEXT = re.compile(
    rf"(?i)"
    rf"(?:"
    rf"(?:must|should|need\s+to|required\s+to)\s+"
    rf"(?:be\s+)?(?:located|based|reside|living|live)\s+"
    rf"(?:in|within)\s+(?:the\s+)?{_GEO_TOKEN}"
    rf"|"
    rf"(?:open\s+to|hiring|candidates?|applicants?|team\s+members?)\s+"
    rf"(?:in|within|from|across)\s+(?:the\s+)?{_GEO_TOKEN}"
    rf"(?:\s+only)?"
    rf"|"
    rf"(?:authorized|authorised|eligible|right)\s+to\s+work\s+in\s+(?:the\s+)?{_GEO_TOKEN}"
    rf"|"
    rf"(?:work\s+authorization|work\s+authorisation|work\s+permit|visa)\s+"
    rf"(?:required\s+)?(?:in|for)\s+(?:the\s+)?{_GEO_TOKEN}"
    rf"|"
    rf"(?:must|should)\s+have\s+(?:the\s+)?(?:right|authorization|authorisation)\s+to\s+work\s+"
    rf"(?:in|within)\s+(?:the\s+)?{_GEO_TOKEN}"
    rf"|"
    rf"{_GEO_TOKEN}\s+(?:only|based)\s+remote"
    rf"|"
    rf"remote\s+(?:roles?\s+)?(?:are\s+)?(?:limited|restricted)\s+to\s+{_GEO_TOKEN}"
    rf"|"
    rf"(?:US|U\.S\.|United\s+States|UK|EU|EEA|Canada)\s+work\s+authorization\s+required"
    rf")"
)

_CITY_LIKE_LOCATION = re.compile(
    r"(?i)^(?!.*\bremote\b)(?!.*\bdistributed\b)(?!.*\bwfh\b)"
    r".{0,80}?(?:"
    r"stockholm|london|berlin|paris|new\s+york|san\s+francisco|seattle|"
    r"toronto|dublin|amsterdam|sydney|tokyo|singapore|munich|zurich|"
    r",\s*(?:[A-Z]{2}|UK|USA|US|CA|NY|WA|TX|CA)\s*$"
    r")"
)

_PLAIN_REMOTE_LOCATIONS = frozenset(
    {
        "remote",
        "fully remote",
        "100% remote",
        "work from home",
        "wfh",
        "distributed",
        "remote first",
        "remote-first",
        "telecommute",
    }
)

_WORLDWIDE_REQUIREMENT_NAMES = frozenset(
    {
        "worldwide",
        "world-wide",
        "global",
        "anywhere",
        "any country",
        "international",
    }
)


def _normalize_requirement_names(value: Any) -> list[str]:
    """Flatten Ashby/schema.org applicantLocationRequirements into name strings."""
    if value is None:
        return []
    names: list[str] = []
    if isinstance(value, str):
        names.append(value.strip())
    elif isinstance(value, dict):
        name = value.get("name") or value.get("addressCountry") or value.get("country")
        if name:
            names.append(str(name).strip())
    elif isinstance(value, (list, tuple)):
        for item in value:
            names.extend(_normalize_requirement_names(item))
    return [n for n in names if n]


def _structured_requirements_block_worldwide(job_dict: dict[str, Any]) -> bool:
    """
    True if structured applicant location requirements restrict to specific countries.
    Empty / missing / worldwide-named requirements do not block.
    """
    raw = job_dict.get("raw") if isinstance(job_dict.get("raw"), dict) else {}
    req = (
        job_dict.get("applicant_location_requirements")
        or job_dict.get("location_requirements")
        or raw.get("applicantLocationRequirements")
        or raw.get("locationRequirements")
    )
    names = _normalize_requirement_names(req)
    if not names:
        return False
    for name in names:
        lower = name.lower().strip()
        if lower in _WORLDWIDE_REQUIREMENT_NAMES:
            continue
        # Any concrete country/region name is a lock
        return True
    return False


def _is_remote_role(loc: str, title: str, desc: str, workplace_type: str | None) -> bool:
    wt = (workplace_type or "").strip().lower().replace("_", "").replace("-", "")
    if wt in {"onsite", "hybrid"}:
        return False
    if wt == "remote":
        return True

    loc_l = (loc or "").strip().lower()
    # Boards like Remotive use location="Worldwide" / "Global" for remote-open roles
    if loc_l in _WORLDWIDE_REQUIREMENT_NAMES or _WORLDWIDE_POSITIVE.search(loc_l):
        return True
    if _REMOTE_WORD.search(loc_l):
        return True
    if loc_l in _PLAIN_REMOTE_LOCATIONS:
        return True

    # City / office location without Remote → not a worldwide-remote listing
    if loc and _CITY_LIKE_LOCATION.search(loc.strip()):
        return False
    if loc and not _REMOTE_WORD.search(loc) and len(loc) <= 80:
        # "Stockholm", "New York, NY", "London", "USA", "Brazil" etc.
        if re.search(r"[A-Za-z]", loc) and not re.search(
            r"(?i)\b(remote|distributed|anywhere|worldwide|world[\s\-]?wide|global)\b",
            loc,
        ):
            return False

    head = f"{loc}\n{title}"
    if _HYBRID_OR_OFFICE.search(head):
        return False
    # Do not treat a buried "remote" mention in a long description as enough
    # when the location field is empty — require stronger workplace signals.
    return bool(_REMOTE_WORD.search(f"{loc}\n{title}"))


def _has_geo_lock(loc: str, desc: str) -> bool:
    if loc and _REGION_LOCKED_LOCATION.search(loc):
        return True
    sample = desc[:16000] if desc else ""
    if sample and _GEO_LOCK_IN_TEXT.search(sample):
        return True
    if loc and _GEO_LOCK_IN_TEXT.search(loc):
        return True
    return False


def _has_worldwide_signal(loc: str, title: str, desc: str) -> bool:
    blob = f"{loc}\n{title}\n{desc[:16000]}"
    return bool(_WORLDWIDE_POSITIVE.search(blob))


def _location_names_specific_geo(loc: str) -> bool:
    """
    True when the location field itself names countries/regions and does NOT
    also say worldwide/anywhere. Used for Remotive-style eligibility locations
    like "USA", "Brazil", "Remote (Canada)" — description fluff must not override.
    """
    if not (loc or "").strip():
        return False
    if _WORLDWIDE_POSITIVE.search(loc):
        return False
    if re.search(rf"(?i)\b{_GEO_TOKEN}\b", loc):
        return True
    # Single/multi token location that isn't a known remote/worldwide keyword
    # (catches uncommon country names not in _GEO_TOKEN)
    cleaned = loc.strip().lower()
    if cleaned in _PLAIN_REMOTE_LOCATIONS or cleaned in _WORLDWIDE_REQUIREMENT_NAMES:
        return False
    if _REMOTE_WORD.search(cleaned) and not re.search(r"[,]|\band\b", cleaned):
        # e.g. "Remote" / "Fully Remote" without a country suffix
        return False
    # "Uruguay", "Kenya", "Portugal Only", etc.
    if re.fullmatch(r"[a-zA-Z][a-zA-Z\s\-'.]{1,40}", loc.strip()):
        return True
    return False


def is_remote_worldwide_listing(job_dict: dict[str, Any]) -> bool:
    """
    Return True only for remote roles that look open to applicants worldwide.

    Rules:
    1. Must be a remote role (workplaceType=Remote or location says remote/distributed/worldwide).
    2. Must NOT have country/region locks in the location field (e.g. Remote US, Brazil, EMEA).
    3. Must NOT have work-auth / "must be located in" locks in description or structured reqs.
    4. Must have an explicit worldwide / work-from-anywhere signal (location or description).
       Plain "Remote" alone is rejected.
    """
    loc = (job_dict.get("location") or "").strip()
    title = (job_dict.get("title") or "").strip()
    desc = job_dict.get("description") or ""
    workplace_type = (
        job_dict.get("workplace_type")
        or (job_dict.get("raw") or {}).get("workplaceType")
        or (job_dict.get("raw") or {}).get("workplace_type")
    )
    desc_text = desc if isinstance(desc, str) else str(desc)
    wt = workplace_type if isinstance(workplace_type, str) else None
    loc_country = (job_dict.get("location_country") or "").strip()

    if not _is_remote_role(loc, title, desc_text, wt):
        return False

    # Hard reject: location names a country/region without worldwide wording
    if _location_names_specific_geo(loc):
        return False

    if _has_geo_lock(loc, ""):
        return False

    if _structured_requirements_block_worldwide(job_dict):
        return False

    if loc_country and loc_country.lower() not in _WORLDWIDE_REQUIREMENT_NAMES:
        if not _WORLDWIDE_POSITIVE.search(loc):
            return False

    if _has_geo_lock(loc, desc_text):
        return False

    if _has_worldwide_signal(loc, title, desc_text):
        return True

    loc_lower = loc.lower().strip()
    if loc_lower in _PLAIN_REMOTE_LOCATIONS:
        return False
    if loc_lower.startswith("remote") and len(loc_lower) <= 80:
        return False

    return False
