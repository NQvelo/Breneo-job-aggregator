"""
Robust job posting parser (standard library only).

Parses any job posting text and outputs:
  - Job Description (short summary, 2–4 sentences)
  - Key Responsibilities (bullets, up to 8)
  - Key Qualifications (bullets, up to 8)

No AI, no external NLP. Works across LinkedIn, Greenhouse, Lever, Workday, blogs, etc.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# A) PREPROCESSING (KEEP NEWLINES!)
# ---------------------------------------------------------------------------


def normalize_newlines(text: str) -> str:
    """Convert CRLF/CR to LF."""
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_trailing_spaces_per_line(text: str) -> str:
    """Strip trailing spaces on each line; preserve line boundaries."""
    if not text:
        return ""
    return "\n".join(line.rstrip() for line in text.split("\n"))


def collapse_repeated_blank_lines(text: str, max_blank: int = 2) -> str:
    """Collapse repeated blank lines to at most max_blank (preserve structure)."""
    if not text:
        return ""
    lines = text.split("\n")
    result: list[str] = []
    blank_count = 0
    for line in lines:
        is_blank = not line.strip()
        if is_blank:
            blank_count += 1
            if blank_count <= max_blank:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)
    return "\n".join(result)


def preprocess(text: str) -> str:
    """Full preprocessing: normalize newlines, strip trailing spaces, collapse blanks."""
    t = normalize_newlines(text)
    t = strip_trailing_spaces_per_line(t)
    t = collapse_repeated_blank_lines(t)
    return t


# ---------------------------------------------------------------------------
# B) HEADING DETECTION (MULTI-SIGNAL SCORING)
# ---------------------------------------------------------------------------

# Separator: 3+ repeated chars
_SEP_PATTERN = re.compile(r"^[\s\-_=\*#]{3,}\s*$")

# ALL CAPS: mostly uppercase letters, few words (e.g. "KEY RESPONSIBILITIES")
def _is_all_caps_short(line: str, max_words: int = 8) -> bool:
    s = line.strip()
    if not s or len(s) > 90:
        return False
    words = s.split()
    if len(words) > max_words:
        return False
    letters = sum(1 for c in s if c.isalpha())
    if letters == 0:
        return False
    upper = sum(1 for c in s if c.isupper())
    return upper >= letters * 0.7


def _normalize_heading_for_keywords(line: str) -> str:
    """Lowercase, remove trailing ':', parentheses, collapse whitespace, fix apostrophes."""
    s = line.strip()
    if s.endswith(":"):
        s = s[:-1].strip()
    s = re.sub(r"\([^)]*\)", " ", s)  # remove parentheticals for matching
    s = s.replace("\u2019", "'").replace("\u2018", "'")  # curly -> straight
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


# Keyword sets for heading classification (used in scoring)
_RESPONSIBILITY_KEYWORDS = frozenset([
    "what you'll do", "what you will do", "responsibilities", "job responsibilities",
    "role responsibilities", "the role", "what you'll be doing", "your impact",
    "key responsibilities", "duties", "day to day", "a typical week", "what you'll work on",
    "what we do", "role and responsibilities", "main responsibilities", "key duties",
    "what you'll own", "your responsibilities", "core responsibilities",
])

_QUALIFICATION_KEYWORDS = frozenset([
    "who you are", "who we're looking for", "what you'll bring", "what you will bring",
    "requirements", "required qualifications", "minimum qualifications",
    "preferred qualifications", "skills", "experience", "what we're looking for",
    "what you need", "you have", "must have", "nice to have", "qualifications",
    "required experience", "desired qualifications", "about you", "you bring",
    "candidate profile", "ideal candidate",
])

_INTRO_KEYWORDS = frozenset([
    "about", "about the role", "job summary", "overview", "the opportunity",
    "team", "the team", "community you will join", "why join", "mission",
    "introduction", "summary", "job description", "the company",
])

_IGNORE_KEYWORDS = frozenset([
    "pay range", "salary", "compensation", "benefits", "perks",
    "your location", "location", "where you'll be", "work location",
    "equal opportunity", "eeo", "inclusion", "belonging", "accommodation",
    "privacy", "how to apply", "application process", "legal", "disclaimer",
    "pay transparency", "applicant", "diversity", "accessibility",
])


def _heading_contains_known_keyword(normalized: str) -> tuple[bool, int]:
    """
    Check if normalized heading contains any known section keyword.
    Returns (matched, points). +2 for any known heading (resp/qual/intro/ignore) so we detect and skip noise.
    """
    n = normalized
    # Check for embedded keywords: e.g. "What You'll Bring (Minimum Qualifications)"
    all_heading_keywords = _RESPONSIBILITY_KEYWORDS | _QUALIFICATION_KEYWORDS | _INTRO_KEYWORDS | _IGNORE_KEYWORDS
    for kw in all_heading_keywords:
        if kw in n:
            return True, 2
    return False, 0


def _title_like_uppercase(line: str) -> bool:
    """Many words start with uppercase (Title Case)."""
    words = [w for w in line.strip().split() if w]
    if len(words) < 2 or len(words) > 12:
        return False
    capped = sum(1 for w in words if w[0].isupper())
    return capped >= min(len(words), 3)


def is_heading(line: str, prev_line: str, next_line: str, threshold: int = 3) -> bool:
    """
    Multi-signal heading detection. Returns True if line is likely a section heading.
    """
    s = line.strip()
    if not s:
        return False

    score = 0

    # Strong: ends with ":"
    if s.endswith(":"):
        score += 3

    # Strong: surrounded by blank lines and reasonable length
    prev_blank = not (prev_line or "").strip()
    next_blank = not (next_line or "").strip()
    if prev_blank and next_blank and 3 <= len(s) <= 85:
        score += 2

    # Strong: separator line
    if _SEP_PATTERN.match(s):
        score += 2

    # Strong: ALL CAPS short
    if _is_all_caps_short(s):
        score += 2

    # Keyword-based: only count if line looks like a title (not a bullet line)
    # so " - Strong Python... skills." is not mistaken for a heading
    normalized = _normalize_heading_for_keywords(s)
    kw_ok, kw_pts = _heading_contains_known_keyword(normalized)
    is_bullet_line = bool(re.match(r"^[\s]*[\-\*\u2022\u2013\d]", s))
    if kw_ok and not is_bullet_line:
        score += kw_pts

    # Title-like
    if _title_like_uppercase(s) and len(s) < 70:
        score += 1

    # Short label-like (e.g. "Benefits", "Location") so we detect and skip noise sections
    if kw_ok and len(normalized) <= 25 and len(normalized.split()) <= 4:
        score += 1

    # Negative: ends with "." and long (sentence)
    if s.endswith(".") and len(s.split()) > 8:
        score -= 2

    # Negative: URL or email only
    if re.match(r"^https?://\S+$", s) or re.match(r"^[\w.\-+]+@[\w.\-]+\.\w+$", s):
        score -= 2

    # Negative: extremely long unless ends with ":" or ALL CAPS
    if len(s) > 90 and not s.endswith(":") and not _is_all_caps_short(s):
        score -= 2

    return score >= threshold


# ---------------------------------------------------------------------------
# C) SECTION PARSING
# ---------------------------------------------------------------------------


@dataclass
class Section:
    title: str
    body_lines: list[str]
    body_text: str = ""

    def __post_init__(self) -> None:
        if not self.body_text and self.body_lines:
            self.body_text = "\n".join(self.body_lines)


def parse_sections(text: str) -> list[Section]:
    """
    Parse preprocessed text into ordered sections.
    First section is __INTRO__. Then each heading starts a new section.
    """
    lines = text.split("\n")
    sections: list[Section] = []
    current_title = "__INTRO__"
    current_body: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        prev = lines[i - 1] if i > 0 else ""
        nxt = lines[i + 1] if i + 1 < len(lines) else ""

        if is_heading(line, prev, nxt):
            # Flush current section
            body_text = "\n".join(current_body).strip()
            if current_title == "__INTRO__" or body_text:
                sections.append(Section(title=current_title, body_lines=current_body.copy(), body_text=body_text))
            current_title = line.strip().rstrip(":")
            current_body = []
        else:
            current_body.append(line)
        i += 1

    # Flush last section
    body_text = "\n".join(current_body).strip()
    if current_title == "__INTRO__" or body_text:
        sections.append(Section(title=current_title, body_lines=current_body.copy(), body_text=body_text))

    return sections


# ---------------------------------------------------------------------------
# D) SECTION TAXONOMY (CLASSIFY)
# ---------------------------------------------------------------------------


def _normalize_section_title(title: str) -> str:
    t = title.strip().lower()
    if t.endswith(":"):
        t = t[:-1].strip()
    t = re.sub(r"\s+", " ", t)
    t = t.replace("\u2019", "'")
    return t


def classify_section(title: str) -> str:
    """
    Returns: "responsibilities" | "qualifications" | "intro" | "ignore" | "other"
    """
    n = _normalize_section_title(title)
    if not n or n == "__intro__":
        return "intro"

    # Check ignore first (substring match for embedded phrases)
    for kw in _IGNORE_KEYWORDS:
        if kw in n:
            return "ignore"

    # Intro before responsibilities so "about the role" etc. map to intro
    for kw in _INTRO_KEYWORDS:
        if kw in n:
            return "intro"

    for kw in _RESPONSIBILITY_KEYWORDS:
        if kw in n:
            return "responsibilities"

    for kw in _QUALIFICATION_KEYWORDS:
        if kw in n:
            return "qualifications"

    return "other"


# ---------------------------------------------------------------------------
# E) BULLET / ITEM EXTRACTION
# ---------------------------------------------------------------------------

_BULLET_MARKERS = re.compile(r"^[\s]*[\-\*\u2022\u2013]\s+", re.UNICODE)
_NUMBERED_MARKER = re.compile(r"^[\s]*\d+[.)\-\s]+\s*", re.UNICODE)


def _strip_bullet_prefix(line: str) -> str:
    s = line.strip()
    s = _BULLET_MARKERS.sub("", s, count=1)
    s = _NUMBERED_MARKER.sub("", s, count=1)
    return s.strip()


def _starts_with_bullet_marker(line: str) -> bool:
    """True if line (stripped) starts with a bullet or numbered marker."""
    s = line.strip()
    if not s:
        return False
    if _BULLET_MARKERS.match(s) or _NUMBERED_MARKER.match(s):
        return True
    return False


def _is_continuation_line(line: str, prev_line: str) -> bool:
    """Indentation heuristic: starts with spaces => continuation, unless it's a new bullet."""
    if not line.strip():
        return True
    # New bullet line is never a continuation
    if _starts_with_bullet_marker(line):
        return False
    if line.startswith((" ", "\t")) and len(line) - len(line.lstrip()) >= 2:
        return True
    # Line ending with , or ; often continues
    if prev_line.rstrip().endswith((",", ";")):
        return True
    return False


def extract_items(section_body_lines: list[str], max_items: int = 12) -> list[str]:
    """
    Extract bullet/list items from section body lines.
    Handles explicit bullets, plain-line bullets, and sentence fallback.
    """
    non_empty = [ln.strip() for ln in section_body_lines if ln.strip()]
    if not non_empty:
        return []

    # Single long paragraph -> sentence fallback
    if len(non_empty) <= 2 and sum(len(l) for l in non_empty) > 250:
        paragraph = " ".join(non_empty)
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        items = [s.strip() for s in sentences if 20 <= len(s.strip()) <= 280][:max_items]
        return _dedupe_items(items)[:max_items]

    items: list[str] = []
    current: list[str] = []
    prev = ""

    for raw in section_body_lines:
        line = raw.rstrip()
        if not line.strip():
            if current:
                item = " ".join(current).strip()
                item = _strip_bullet_prefix(item)
                if 20 <= len(item) <= 280 and not item.endswith(":"):
                    items.append(item)
                current = []
            prev = line
            continue

        if current and _is_continuation_line(line, prev):
            current.append(line.strip())
        else:
            if current:
                item = " ".join(current).strip()
                item = _strip_bullet_prefix(item)
                if 20 <= len(item) <= 280 and not item.endswith(":"):
                    items.append(item)
                current = []

            stripped = _strip_bullet_prefix(line)
            # Plain-line bullet: reasonable length, not a heading
            if 20 <= len(stripped) <= 240 and not stripped.endswith(":"):
                current = [stripped]
            else:
                current = [stripped]

        prev = line

    if current:
        item = " ".join(current).strip()
        item = _strip_bullet_prefix(item)
        if 20 <= len(item) <= 280 and not item.endswith(":"):
            items.append(item)

    return _dedupe_items(items)[:max_items]


def _dedupe_items(items: list[str]) -> list[str]:
    """Deduplicate while preserving order (case-insensitive, strip)."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        key = x.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(x.strip())
    return out


# ---------------------------------------------------------------------------
# F) JOB DESCRIPTION SUMMARY & FALLBACKS (NEVER EMPTY WHEN RAW TEXT EXISTS)
# ---------------------------------------------------------------------------


def _fallback_bullet_items_from_text(text: str, max_items: int = 8) -> list[str]:
    """
    Derive bullet items from raw text when section parsing finds nothing.
    Splits by paragraphs first, then by sentences; keeps items 20–240 chars.
    """
    if not text or not text.strip():
        return []
    text = text.strip()
    # Prefer paragraphs (double newline)
    paras = [p.strip() for p in text.split("\n\n") if p.strip() and len(p.strip()) >= 20]
    items: list[str] = []
    for p in paras:
        if len(p) <= 240 and not p.endswith(":"):
            items.append(p)
        else:
            # Split long paragraph into sentences
            parts = re.split(r"(?<=[.!?])\s+", p)
            for part in parts:
                part = part.strip()
                if 20 <= len(part) <= 240 and not part.endswith(":"):
                    items.append(part)
        if len(items) >= max_items:
            break
    if len(items) < max_items and not paras:
        # No paragraphs: split by sentences
        parts = re.split(r"(?<=[.!?])\s+", text)
        for p in parts:
            p = p.strip()
            if 20 <= len(p) <= 240 and not p.endswith(":"):
                items.append(p)
                if len(items) >= max_items:
                    break
    return _dedupe_items(items)[:max_items]


_JOB_DESC_MAX_CHARS = 600

# Patterns to strip from job description (pay, location constraints, EEO/legal text)
_JOB_DESC_EXCLUDE_PATTERNS = [
    r'\$[\d,]+(?:k|K)?(?:\s*[-–—]\s*\$?[\d,]+(?:k|K)?)?',
    r'\d+\s*[-–—]\s*\d+\s*(?:k|K)\s*(?:USD|EUR|salary|pay)?',
    r'\b(?:usd|eur|gbp)\s*[\d,]+\s*[-–—]',
    r'\b(?:remote|hybrid|onsite|in-office)\b.*\b(?:only|eligible|required|must)\b',
    r'\b(?:equal opportunity|eeo|affirmative action|inclusion|accommodation)\b',
    r'\b(?:privacy policy|legal notice|disclaimer|applicant)\b',
    r'\b(?:pay transparency|salary transparency)\b',
]


def _strip_excluded_from_text(text: str) -> str:
    """Remove pay, location constraints, EEO/legal phrases from text."""
    if not text or not text.strip():
        return text
    result = text
    for pattern in _JOB_DESC_EXCLUDE_PATTERNS:
        result = re.sub(pattern, ' ', result, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', result).strip()


def _first_n_sentences(text: str, n: int = 4, min_chars: int = 80) -> str:
    """Extract first n sentences from text (by splitting on . ! ?)."""
    if not text or not text.strip():
        return ""
    text = text.strip()
    # Split on sentence boundaries
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentences = [p.strip() for p in parts if p.strip() and len(p.strip()) >= 10]
    chosen = sentences[:n]
    result = " ".join(chosen)
    if len(result) < min_chars and sentences:
        result = " ".join(sentences[: min(n + 2, len(sentences))])
    return result.strip()


def _trim_to_max_chars_at_sentence(text: str, max_chars: int = _JOB_DESC_MAX_CHARS) -> str:
    """Trim text to max_chars at sentence boundaries."""
    if not text or len(text) <= max_chars:
        return text.strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    result: list[str] = []
    length = 0
    for s in parts:
        s = s.strip()
        if not s or len(s) < 10:
            continue
        if length + len(s) + 1 <= max_chars:
            result.append(s)
            length += len(s) + 1
        else:
            break
    return " ".join(result).strip() if result else text[:max_chars].rsplit('.', 1)[0].strip() + '.'


def build_job_description_summary(sections: list[Section]) -> str:
    """
    Build SHORT, clear job description (2–4 sentences max, ~600 char cap).
    Excludes: responsibilities/qualifications, pay, location, EEO/legal text.
    Uses simple language describing what the role does and its impact.
    """
    candidate_parts: list[str] = []
    for sec in sections:
        kind = classify_section(sec.title)
        if kind in ("ignore", "responsibilities", "qualifications"):
            continue
        if sec.body_text and len(sec.body_text) > 30:
            candidate_parts.append(sec.body_text)

    combined = " ".join(candidate_parts)
    if not combined.strip():
        return ""
    # Strip excluded content (pay, location, EEO, etc.)
    cleaned = _strip_excluded_from_text(combined)
    if not cleaned:
        return ""
    summary = _first_n_sentences(cleaned, n=4, min_chars=60)
    return _trim_to_max_chars_at_sentence(summary, _JOB_DESC_MAX_CHARS)


# ---------------------------------------------------------------------------
# MAIN PARSER API
# ---------------------------------------------------------------------------


@dataclass
class ParsedJobPosting:
    job_description: str = ""
    key_responsibilities: list[str] = field(default_factory=list)
    key_qualifications: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_description": self.job_description,
            "key_responsibilities": self.key_responsibilities[:8],
            "key_qualifications": self.key_qualifications[:8],
        }


def parse_job_posting(raw_text: str) -> ParsedJobPosting:
    """
    Parse raw job posting text into structured job description, responsibilities, qualifications.
    Returns a ParsedJobPosting (use .to_dict() for dict output).
    """
    text = preprocess(raw_text or "")
    sections = parse_sections(text)

    responsibilities: list[str] = []
    qualifications: list[str] = []

    for sec in sections:
        kind = classify_section(sec.title)
        if kind == "ignore":
            continue
        items = extract_items(sec.body_lines, max_items=12)
        if kind == "responsibilities":
            responsibilities.extend(items)
        elif kind == "qualifications":
            qualifications.extend(items)

    job_desc = build_job_description_summary(sections)
    if not job_desc and sections:
        first = sections[0]
        if first.body_text:
            cleaned = _strip_excluded_from_text(first.body_text)
            if cleaned:
                job_desc = _trim_to_max_chars_at_sentence(
                    _first_n_sentences(cleaned, n=4, min_chars=60),
                    _JOB_DESC_MAX_CHARS
                )
    # Fallback: use full text so we never return empty when raw text exists
    if not job_desc and text.strip():
        cleaned = _strip_excluded_from_text(text)
        if cleaned:
            job_desc = _trim_to_max_chars_at_sentence(
                _first_n_sentences(cleaned, n=4, min_chars=60),
                _JOB_DESC_MAX_CHARS
            )

    resp_list = _dedupe_items(responsibilities)[:8]
    qual_list = _dedupe_items(qualifications)[:8]
    if not resp_list and text.strip():
        resp_list = _fallback_bullet_items_from_text(text, max_items=8)
    if not qual_list and text.strip():
        qual_list = _fallback_bullet_items_from_text(text, max_items=8)

    return ParsedJobPosting(
        job_description=job_desc,
        key_responsibilities=resp_list,
        key_qualifications=qual_list,
    )


def parse_job_posting_for_db(
    raw_text: str,
    *,
    bullet: str = "• ",
    use_short_description: bool = False,
) -> dict[str, Any]:
    """
    Parse raw job posting and return a dict ready for Job model fields.

    Use this to auto-fill description (optional), responsibilities, and qualifications
    in the database. Keeps full raw text in description unless use_short_description=True.

    Returns:
        dict with:
          - job_description_summary: 2–4 sentence summary (for structured_description['summary'])
          - responsibilities: single string, newline-separated bullets (for Job.responsibilities)
          - qualifications: single string (for Job.qualifications)
          - description: short summary only if use_short_description=True, else None
    """
    raw = (raw_text or "").strip()
    parsed = parse_job_posting(raw_text or "")

    # Always format as bullets (• prefix) and ensure nothing is empty when raw text exists
    def to_bullet_block(lines: list[str]) -> str:
        if not lines:
            return ""
        return "\n".join((bullet + line).strip() if line.strip() else line for line in lines).strip()

    resp_text = to_bullet_block(parsed.key_responsibilities)
    qual_text = to_bullet_block(parsed.key_qualifications)
    summary = parsed.job_description or ""

    if raw:
        preprocessed = preprocess(raw)
        if not summary and preprocessed.strip():
            cleaned = _strip_excluded_from_text(preprocessed)
            if cleaned:
                summary = _trim_to_max_chars_at_sentence(
                    _first_n_sentences(cleaned, n=4, min_chars=60),
                    _JOB_DESC_MAX_CHARS
                )
        if not resp_text and preprocessed.strip():
            fallback = _fallback_bullet_items_from_text(preprocessed, max_items=8)
            resp_text = to_bullet_block(fallback)
        if not qual_text and preprocessed.strip():
            fallback = _fallback_bullet_items_from_text(preprocessed, max_items=8)
            qual_text = to_bullet_block(fallback)

    out: dict[str, Any] = {
        "job_description_summary": summary,
        "responsibilities": resp_text,
        "qualifications": qual_text,
    }
    if use_short_description and summary:
        out["description"] = summary
    return out


def print_parsed(parsed: ParsedJobPosting) -> None:
    """Pretty-print parsed job posting to stdout."""
    print("=" * 60)
    print("JOB DESCRIPTION")
    print("=" * 60)
    print(parsed.job_description or "(none)")
    print()
    print("KEY RESPONSIBILITIES")
    print("-" * 40)
    for i, r in enumerate(parsed.key_responsibilities, 1):
        print(f"  {i}. {r}")
    if not parsed.key_responsibilities:
        print("  (none)")
    print()
    print("KEY QUALIFICATIONS")
    print("-" * 40)
    for i, q in enumerate(parsed.key_qualifications, 1):
        print(f"  {i}. {q}")
    if not parsed.key_qualifications:
        print("  (none)")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI-like demo
# ---------------------------------------------------------------------------

def demo(raw_text: str | None = None) -> None:
    """
    Demo: parse sample or provided text and print result + dict.
    Example usage:
        from jobs.job_posting_parser import demo, parse_job_posting
        demo()  # runs on built-in sample
        demo("paste job text here")
        result = parse_job_posting("...")
        print(result.to_dict())
    """
    sample = raw_text or """
    About the Role

    We are looking for a Senior Software Engineer to help build our platform.

    What You'll Do

    - Design and implement new features in Python and React.
    - Collaborate with product and design teams.
    - Mentor junior engineers and do code reviews.
    - Own services end-to-end from design to production.

    What You'll Bring

    - 5+ years of software engineering experience.
    - Strong Python and JavaScript/TypeScript skills.
    - Experience with AWS or GCP.
    - Nice to have: React, Docker, Kubernetes.

    Benefits

    Health, dental, 401k.

    Equal Opportunity Employer. We welcome all applicants.
    """
    parsed = parse_job_posting(sample)
    print_parsed(parsed)
    print("\nAs dict:")
    print(parsed.to_dict())


if __name__ == "__main__":
    # Example: python -m jobs.job_posting_parser
    # Or pass a file path: python -m jobs.job_posting_parser path/to/posting.txt
    if len(sys.argv) > 1:
        path = sys.argv[1]
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            parsed = parse_job_posting(text)
            print_parsed(parsed)
            print("\nDict:", parsed.to_dict())
        except FileNotFoundError:
            print("File not found:", path, file=sys.stderr)
            sys.exit(1)
    else:
        demo()
