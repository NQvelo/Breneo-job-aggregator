"""
Heuristic: job listing is remote and open worldwide (not region-locked remote).

Used by fetch_jobs --remote-worldwide-only. ATS location strings vary; this errs on the
side of excluding borderline region-specific remotes.
"""

from __future__ import annotations

import re
from typing import Any

_REMOTE_WORD = re.compile(r"\b(remote|wfh|work\s+from\s+home)\b", re.I)
_HYBRID_OR_OFFICE = re.compile(
    r"\b(hybrid|on-?site|in-?office|office-?based|in-?person)\b",
    re.I,
)
_WORLDWIDE = re.compile(
    r"\b("
    r"worldwide|world-wide|globally|work\s+from\s+anywhere|anywhere\s+in\s+the\s+world|"
    r"fully\s+distributed|distributed\s+team|remote\s+first|international|"
    r"all\s+time\s+zones|no\s+office|100%\s+remote|fully\s+remote"
    r")\b",
    re.I,
)
# "Remote" tied to a specific country/region in the location line
_REGION_LOCKED_REMOTE = re.compile(
    r"remote\s*"
    r"([,;|/()\[\]:\-–—]|\s+in\s+|\s+from\s+|\s+for\s+|\s+within\s+)"
    r".{0,120}?"
    r"\b("
    r"united\s+states|u\.s\.a?\.?|\busa\b|\bus\b|america(?!\s+latina)|"
    r"united\s+kingdom|u\.k\.|\buk\b|england|scotland|wales|ireland|"
    r"canada|germany|france|spain|italy|india|brazil|mexico|japan|china|"
    r"australia|new\s+zealand|netherlands|belgium|austria|switzerland|sweden|norway|"
    r"poland|portugal|israel|singapore|south\s+korea|hong\s+kong|"
    r"emea|apac|latam|eea\b|\beu\b|europe|north\s+america|latin\s+america|"
    r"california|texas|florida|new\s+york|washington\s+dc|colorado|illinois|"
    r"\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|"
    r"MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|"
    r"WA|WV|WI|WY|DC)\b"
    r")\b",
    re.I,
)

_PLAIN_REMOTE_LOCATIONS = frozenset(
    {
        "remote",
        "fully remote",
        "100% remote",
        "work from home",
        "wfh",
        "distributed",
        "remote — worldwide",
        "remote - worldwide",
        "remote worldwide",
        "remote, worldwide",
        "remote (worldwide)",
        "remote (global)",
        "remote global",
        "remote, global",
    }
)


def is_remote_worldwide_listing(job_dict: dict[str, Any]) -> bool:
    loc = (job_dict.get("location") or "").strip()
    title = (job_dict.get("title") or "").strip()
    desc = (job_dict.get("description") or "")[:12000]
    head = f"{loc}\n{title}".lower()
    blob = f"{loc}\n{title}\n{desc}".lower()

    if _HYBRID_OR_OFFICE.search(head):
        return False
    if not _REMOTE_WORD.search(blob):
        return False

    loc_lower = loc.lower()
    if _REGION_LOCKED_REMOTE.search(loc_lower):
        return False

    if _WORLDWIDE.search(loc_lower) or _WORLDWIDE.search(blob):
        return True

    if loc_lower in _PLAIN_REMOTE_LOCATIONS:
        return True

    # Short location that is only "Remote" variants without a region suffix
    if loc_lower.startswith("remote") and len(loc_lower) <= 64:
        if not _REGION_LOCKED_REMOTE.search(loc_lower):
            return True

    return False
