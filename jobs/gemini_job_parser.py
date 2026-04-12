"""
Gemini-based parsing for employer-manual job descriptions (Breneo).

Used only when platform is employer and raw.source is employer / employer_manual.
API key: GEMINI_API_KEY (never exposed to clients).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# No artificial “6 bullet” cap: keep every distinct item (high ceiling avoids abuse-sized responses).
MAX_RESPONSIBILITIES = 500
MAX_QUALIFICATIONS = 500
MAX_SKILLS = 20
ITEM_MAX_LEN = 500

# Flash model (override via GEMINI_MODEL)
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


def is_employer_manual_job(job) -> bool:
    """
    True only for jobs created/edited through the employer UI (Breneo manual posts).

    Fetched/imported jobs use platform greenhouse, lever, etc. — never Gemini.
    """
    if getattr(job, "platform", None) != "employer":
        return False
    raw = job.raw if isinstance(job.raw, dict) else {}
    src = str(raw.get("source") or "").strip().lower()
    return src in ("employer", "employer_manual")


def _lines_to_bullet_text(lines: list[str]) -> str:
    if not lines:
        return ""
    out = []
    for ln in lines:
        t = (ln or "").strip()
        if t:
            out.append(f"• {t}")
    return "\n".join(out).strip()


def _strip_json_fence(text: str) -> str:
    s = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", s, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return s


def _strip_contact_noise(s: str) -> str:
    """Remove emails / phone-like patterns from a single line (safety net)."""
    if not s:
        return s
    s = re.sub(r"\S+@\S+\.\S+", "", s)
    s = re.sub(r"\+?\d[\d\s\-().]{7,}\d", "", s)
    return re.sub(r"\s+", " ", s).strip(" ,;.")


def validate_and_normalize_parsed(data: Any) -> dict[str, list[str]]:
    """
    Ensure shape { responsibilities, qualifications, skills_required } with sane limits.
    skills_required: deduped, sorted alphabetically (case-insensitive).
    """
    empty = {"responsibilities": [], "qualifications": [], "skills_required": []}
    if not isinstance(data, dict):
        return empty

    def norm_list(key: str, max_n: int) -> list[str]:
        raw = data.get(key)
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for x in raw:
            if not isinstance(x, str):
                continue
            t = _strip_contact_noise(x.strip())[:ITEM_MAX_LEN]
            if not t:
                continue
            low = t.lower()
            if low in seen:
                continue
            seen.add(low)
            out.append(t)
            if len(out) >= max_n:
                break
        return out

    resp = norm_list("responsibilities", MAX_RESPONSIBILITIES)
    qual = norm_list("qualifications", MAX_QUALIFICATIONS)
    skills = norm_list("skills_required", MAX_SKILLS)
    skills = sorted(set(skills), key=str.lower)
    return {
        "responsibilities": resp,
        "qualifications": qual,
        "skills_required": skills[:MAX_SKILLS],
    }


def _build_prompt(description: str, strict_retry: bool) -> str:
    core = """You are a job posting extractor for Breneo. Input may be any language.

Return ONLY a JSON object (no markdown fences, no commentary) with exactly these keys:
"responsibilities", "qualifications", "skills_required"

Each value is an array of strings.

LANGUAGE RULES:
- responsibilities: each string must be professional, natural Georgian (translate if needed). Action-focused duties only.
- qualifications: each string must be professional Georgian (translate if needed). Real requirements only.
- skills_required: English ONLY. Standard tech names (Python, React, AWS). Only skills EXPLICITLY mentioned in the input text. Do NOT infer or guess technologies. If a skill is not clearly written, omit it. Normalize spelling (e.g. პითონი -> Python).

EXTRACTION RULES:
- responsibilities: real job duties only (what the hire will do). Include EVERY distinct duty as its own string — do NOT limit the number of bullets; never truncate the list for brevity. No benefits, slogans, mission, marketing, HR fluff, company values, perks, salary, legal text, application instructions, contact info.
- qualifications: years of experience, education, tools, languages, certifications, clearly stated soft skills if required. Include EVERY distinct requirement as its own string — do NOT limit the number of bullets; never truncate. No vague personality traits.
- skills_required: programming languages, frameworks, libraries, cloud/DevOps tools, databases, platforms, explicit methodologies (CI/CD, Agile, Scrum) only if literally stated. Max 20 items, sorted alphabetically in English. No communication/teamwork/leadership as skills.

FILTER: Remove emails, phone numbers, hashtags, salary figures, legal/disclaimer text from all strings.

If the description lacks usable content for a section, use an empty array for that section.

Job description:
"""
    if strict_retry:
        core = (
            "CRITICAL: Output a single JSON object only. No markdown. No text before or after. "
            "Schema: {\"responsibilities\":[],\"qualifications\":[],\"skills_required\":[]}\n\n"
        ) + core
    return core + "\n---\n" + (description or "").strip()


def _response_text(response: Any) -> str:
    """Best-effort extract text from google-generativeai response."""
    if response is None:
        return ""
    t = getattr(response, "text", None)
    if t:
        return str(t)
    try:
        c = response.candidates[0].content
        parts = getattr(c, "parts", None) or []
        return "".join(getattr(p, "text", "") or "" for p in parts)
    except (IndexError, AttributeError, TypeError):
        return ""


def _parse_json_response(text: str) -> Any:
    raw = _strip_json_fence(text)
    return json.loads(raw)


def parse_job_description_with_gemini(
    description: str,
    *,
    strict_retry: bool = False,
) -> dict[str, list[str]]:
    """
    Call Gemini and return validated { responsibilities, qualifications, skills_required }.
    On any failure, returns three empty lists (never raises to callers).
    """
    api_key = (getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY", "") or "").strip()
    if not api_key or not (description or "").strip():
        return {"responsibilities": [], "qualifications": [], "skills_required": []}

    model_name = (
        getattr(settings, "GEMINI_MODEL", None) or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
    ).strip()

    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai is not installed; cannot run Gemini job parser")
        return {"responsibilities": [], "qualifications": [], "skills_required": []}

    genai.configure(api_key=api_key)
    prompt = _build_prompt(description, strict_retry=strict_retry)

    try:
        try:
            gen_cfg = genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )
        except Exception:
            gen_cfg = {"response_mime_type": "application/json", "temperature": 0.2}
        model = genai.GenerativeModel(model_name)
        timeout = int(getattr(settings, "GEMINI_TIMEOUT_SECONDS", 90) or 90)
        response = model.generate_content(
            prompt,
            generation_config=gen_cfg,
            request_options={"timeout": timeout},
        )
        text = _response_text(response)
        data = _parse_json_response(text)
        return validate_and_normalize_parsed(data)
    except Exception as e:
        logger.warning("Gemini job parse failed: %s", e, exc_info=False)
        if not strict_retry:
            return parse_job_description_with_gemini(description, strict_retry=True)
        return {"responsibilities": [], "qualifications": [], "skills_required": []}


def apply_parsed_to_job(job, parsed: dict[str, list[str]]) -> None:
    """Write validated parse result onto Job instance (does not save)."""
    parsed = validate_and_normalize_parsed(parsed)
    job.responsibilities = _lines_to_bullet_text(parsed["responsibilities"]) or None
    job.qualifications = _lines_to_bullet_text(parsed["qualifications"]) or None
    job.skills_required = parsed["skills_required"]


def maybe_parse_employer_description_with_gemini(job) -> bool:
    """
    If this is an employer-manual job and GEMINI_API_KEY is set, fill responsibilities,
    qualifications, skills_required from Gemini. Returns True if an API attempt was made
    (including when the model returns empty lists). Returns False if skipped (no key / no text / wrong source).
    """
    if not is_employer_manual_job(job):
        return False
    desc = (job.description or "").strip()
    if not desc:
        return False
    api_key = (getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        return False
    parsed = parse_job_description_with_gemini(desc)
    apply_parsed_to_job(job, parsed)
    return True
