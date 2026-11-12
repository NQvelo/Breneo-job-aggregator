"""
AI summary of fetched job postings (server side only).

For each posting the model returns a short summary, concise responsibilities and qualifications,
and the skills and tools the role asks for. Every skill must come with a verbatim quote from the
posting; skills whose quote is not in the text are dropped, so the model cannot invent tools
(e.g. from the company's own product blurb).

Providers, in order: Groq's free chat models (GROQ_API_KEY), then Gemini (GEMINI_API_KEY). Free
tiers are limited by tokens per minute and per day, so each Groq model is paced to its per-minute
budget and set aside for the run once its daily budget is used; when every provider is used up,
`AIQuotaExhausted` is raised and the remaining jobs wait for the next run.

The result is stored on the job together with a fingerprint of title + description, so the daily
fetch keeps it as long as the posting text is unchanged (see `reapply_ai_fields`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import deque
from typing import Any

import httpx
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Bump when the prompt or output shape changes, so stored results are regenerated.
AI_ENRICHMENT_VERSION = 1

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# Groq free tier per model: 30 RPM, 1K RPD, 8K TPM, 200K TPD (console.groq.com/docs/rate-limits).
DEFAULT_GROQ_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b")
DEFAULT_GROQ_TPM = 8000
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Posting text sent to the model, in estimated tokens. Keeps one job at ~2.5K tokens in total.
DEFAULT_MAX_INPUT_TOKENS = 1500
MAX_OUTPUT_TOKENS = 1200

MAX_SUMMARY_CHARS = 600
MAX_BULLETS = 8
MAX_BULLET_CHARS = 220
MAX_SKILLS = 20
MAX_SKILL_CHARS = 60

_PROMPT = """You summarize one job posting for a job board. The posting may be in any language.

Write "summary", "responsibilities" and "qualifications" in the SAME language as the posting.

- summary: 2-3 plain sentences: what the role is, the team or product it works on, and the level.
  No company marketing, no benefits, no salary, no application instructions.
- responsibilities: at most 8 short bullets (one line each) of what the hire will actually do.
  Merge similar duties. Leave out company history, mission, values, perks and hiring process.
- qualifications: at most 8 short bullets of what the hire must or should have: years of experience,
  education, languages, certifications, domain knowledge.
- skills_required: hard skills, technologies, methods and professional software the role REQUIRES.
- skills_preferred: hard skills listed as nice to have / bonus / preferred.
- tools: specific software, platforms or equipment the hire will use (e.g. Jira, Figma, Salesforce,
  QuickBooks, Excel, AutoCAD, an EHR system) that are not already in the two skills lists.

Rules for skills_required, skills_preferred and tools:
- Use the standard English name ("Python", "PostgreSQL", "Google Ads", "Microsoft Excel"), max 20 per list.
- Only include an item that the posting asks of THIS role. Do NOT include tools that only appear in the
  company description, its product, its customers, or its integrations list.
- Do NOT include soft skills (communication, teamwork, leadership) or spoken languages.
- "evidence" must be an exact, short quote (1-6 words) copied from the posting that names the item.
  If you cannot quote it, leave the item out.

If a section has no content in the posting, return an empty string or empty list for it.

Return ONLY this JSON object:
{{"summary": "", "responsibilities": [], "qualifications": [],
 "skills_required": [{{"name": "", "evidence": ""}}],
 "skills_preferred": [{{"name": "", "evidence": ""}}],
 "tools": [{{"name": "", "evidence": ""}}]}}

Job title: {title}

Posting:
---
{description}
---"""

_ITEM = {"type": "STRING"}
_SKILL = {
    "type": "OBJECT",
    "properties": {"name": {"type": "STRING"}, "evidence": {"type": "STRING"}},
    "required": ["name", "evidence"],
}
GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "responsibilities": {"type": "ARRAY", "items": _ITEM},
        "qualifications": {"type": "ARRAY", "items": _ITEM},
        "skills_required": {"type": "ARRAY", "items": _SKILL},
        "skills_preferred": {"type": "ARRAY", "items": _SKILL},
        "tools": {"type": "ARRAY", "items": _SKILL},
    },
    "required": ["summary", "responsibilities", "qualifications", "skills_required", "skills_preferred", "tools"],
}


class AIQuotaExhausted(Exception):
    """Every configured provider has used its daily budget (or none is configured)."""


class _DailyLimit(Exception):
    pass


# --- Settings ---------------------------------------------------------------------------------

def _setting(name: str, default: str = "") -> str:
    return str(getattr(settings, name, None) or os.environ.get(name, "") or default).strip()


def _groq_key() -> str:
    return _setting("GROQ_API_KEY")


def _gemini_key() -> str:
    return _setting("GEMINI_API_KEY")


def _groq_models() -> list[str]:
    raw = _setting("GROQ_ENRICHMENT_MODELS")
    return [m.strip() for m in raw.split(",") if m.strip()] if raw else list(DEFAULT_GROQ_MODELS)


def _gemini_model() -> str:
    return _setting("GEMINI_ENRICHMENT_MODEL") or _setting("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def ai_enrichment_enabled() -> bool:
    return bool(_groq_key() or _gemini_key())


# --- Token budgeting --------------------------------------------------------------------------

_GEORGIAN = re.compile(r"[\u10a0-\u10ff]")


def estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token for Latin text, ~1.3 for Georgian script."""
    text = text or ""
    geo = len(_GEORGIAN.findall(text))
    return int((len(text) - geo) / 4 + geo / 1.3) + 1


def _is_heading(line: str) -> bool:
    s = line.strip()
    return 0 < len(s) <= 60 and not s.endswith((".", ",", ";")) and not s.startswith(("-", "•", "*"))


def trim_posting(description: str, max_tokens: int) -> str:
    """Drop company / benefits / legal sections, then cut the text to roughly max_tokens."""
    from .job_normalizer import _IGNORED_HEADINGS

    kept: list[str] = []
    skipping = False
    for line in (description or "").splitlines():
        if _is_heading(line):
            skipping = bool(_IGNORED_HEADINGS.match(line.strip()))
            if skipping:
                continue
        if not skipping:
            kept.append(line)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip() or (description or "").strip()
    if estimate_tokens(text) <= max_tokens:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo]


class _GroqModelPool:
    """Picks a Groq model with room in its per-minute token budget; tracks models out for the day."""

    def __init__(self, models: list[str], tpm: int):
        self.models = models
        self.tpm = tpm
        self.lock = threading.Lock()
        self.usage: dict[str, deque] = {m: deque() for m in models}
        self.exhausted: set[str] = set()

    def _used(self, model: str, now: float) -> int:
        q = self.usage[model]
        while q and now - q[0][0] >= 60:
            q.popleft()
        return sum(n for _, n in q)

    def acquire(self, tokens: int) -> str | None:
        """Reserve tokens on a model, waiting for minute budget if needed. None when all are out for the day."""
        tokens = min(tokens, self.tpm)
        while True:
            with self.lock:
                now = time.monotonic()
                live = [m for m in self.models if m not in self.exhausted]
                if not live:
                    return None
                for m in live:
                    if self._used(m, now) + tokens <= self.tpm:
                        self.usage[m].append((now, tokens))
                        return m
                waits = [60 - (now - self.usage[m][0][0]) for m in live if self.usage[m]]
            time.sleep(max(0.5, min(waits or [1.0])))

    def settle(self, model: str, reserved: int, actual: int | None) -> None:
        if actual is None:
            return
        reserved = min(reserved, self.tpm)
        with self.lock:
            q = self.usage[model]
            for i in range(len(q) - 1, -1, -1):
                if q[i][1] == reserved:
                    q[i] = (q[i][0], actual)
                    break

    def mark_exhausted(self, model: str) -> None:
        with self.lock:
            self.exhausted.add(model)

    def all_exhausted(self) -> bool:
        with self.lock:
            return all(m in self.exhausted for m in self.models)


_pool: _GroqModelPool | None = None
_pool_lock = threading.Lock()
_gemini_exhausted = threading.Event()


def _groq_pool() -> _GroqModelPool:
    global _pool
    with _pool_lock:
        models = _groq_models()
        if _pool is None or _pool.models != models:
            _pool = _GroqModelPool(models, int(_setting("GROQ_ENRICHMENT_TPM", str(DEFAULT_GROQ_TPM))))
        return _pool


def reset_provider_state() -> None:
    """Forget per-run quota state (start of each enrichment run, and in tests)."""
    global _pool
    with _pool_lock:
        _pool = None
    _gemini_exhausted.clear()


# --- Providers --------------------------------------------------------------------------------

def _strip_reasoning(text: str) -> str:
    text = re.sub(r"<think>[\s\S]*?</think>", "", text or "").strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", text, re.IGNORECASE)
    return m.group(1).strip() if m else text


def _groq_once(model: str, prompt: str) -> tuple[Any, int | None]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
    }
    if model.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
    timeout = int(_setting("GROQ_TIMEOUT_SECONDS", "60"))
    for attempt in range(4):
        r = httpx.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {_groq_key()}"},
            json=payload,
            timeout=timeout,
        )
        if r.status_code == 429:
            message = r.text.lower()
            if "per day" in message or "(tpd)" in message or "(rpd)" in message:
                raise _DailyLimit(model)
            time.sleep(min(float(r.headers.get("retry-after") or 5 * (attempt + 1)), 60))
            continue
        if r.status_code >= 500 and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"].get("content") or ""
        return json.loads(_strip_reasoning(content)), (data.get("usage") or {}).get("total_tokens")
    raise httpx.HTTPError(f"Groq {model}: still rate limited after retries")


def _call_groq(prompt: str) -> tuple[Any, str] | None:
    """(parsed JSON, model) from the first Groq model with budget; None when all are out for the day."""
    pool = _groq_pool()
    reserved = estimate_tokens(prompt) + MAX_OUTPUT_TOKENS
    while True:
        model = pool.acquire(reserved)
        if model is None:
            return None
        try:
            data, used = _groq_once(model, prompt)
        except _DailyLimit:
            logger.info("Groq %s reached its daily limit; trying the next model", model)
            pool.mark_exhausted(model)
            continue
        pool.settle(model, reserved, used)
        return data, f"groq:{model}"


def _call_gemini(prompt: str) -> tuple[Any, str] | None:
    if _gemini_exhausted.is_set():
        return None
    model = _gemini_model()
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": GEMINI_RESPONSE_SCHEMA,
        },
    }
    timeout = int(getattr(settings, "GEMINI_TIMEOUT_SECONDS", 90) or 90)
    for attempt in range(3):
        r = httpx.post(f"{GEMINI_API_BASE}/{model}:generateContent", params={"key": _gemini_key()},
                       json=body, timeout=timeout)
        if r.status_code == 429:
            if "perday" in r.text.lower().replace("_", "").replace(" ", "") or attempt == 2:
                logger.info("Gemini %s reached its quota; stopping AI summaries for this run", model)
                _gemini_exhausted.set()
                return None
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code >= 500 and attempt < 2:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        return json.loads("".join(p.get("text", "") for p in parts)), f"gemini:{model}"
    return None


def _generate(prompt: str) -> tuple[Any, str]:
    if _groq_key():
        out = _call_groq(prompt)
        if out is not None:
            return out
    if _gemini_key():
        out = _call_gemini(prompt)
        if out is not None:
            return out
    raise AIQuotaExhausted("No AI provider has budget left")


# --- Validation -------------------------------------------------------------------------------

def description_fingerprint(title: str | None, description: str | None) -> str:
    text = f"{AI_ENRICHMENT_VERSION}\n{(title or '').strip()}\n{(description or '').strip()}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _clean_line(s: Any, max_len: int) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\S+@\S+\.\S+", "", s)
    s = re.sub(r"^[\s•\-–*·]+", "", s)
    return re.sub(r"\s+", " ", s).strip()[:max_len]


def _clean_bullets(items: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items if isinstance(items, list) else []:
        line = _clean_line(item, MAX_BULLET_CHARS)
        if line and line.lower() not in seen:
            seen.add(line.lower())
            out.append(line)
        if len(out) >= MAX_BULLETS:
            break
    return out


def _canonical_skill(name: str) -> str:
    from .job_normalizer import get_skill_alias_index

    return get_skill_alias_index().get(name.lower(), name)


def _verified_skills(items: Any, source_text: str, exclude: set[str]) -> list[str]:
    """Keep skills whose quoted evidence (or name) occurs in the posting; map to catalog names."""
    out: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_line(item.get("name"), MAX_SKILL_CHARS)
        evidence = _squash(item.get("evidence") or "")
        if not name:
            continue
        if not ((evidence and evidence in source_text) or _squash(name) in source_text):
            continue
        canonical = _canonical_skill(name)
        if canonical.lower() in exclude:
            continue
        exclude.add(canonical.lower())
        out.append(canonical)
        if len(out) >= MAX_SKILLS:
            break
    return sorted(out, key=str.lower)


def validate_ai_result(data: Any, description: str, title: str = "") -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    source = _squash(f"{title}\n{description}")
    seen: set[str] = set()
    required = _verified_skills(data.get("skills_required"), source, seen)
    preferred = _verified_skills(data.get("skills_preferred"), source, seen)
    tools = _verified_skills(data.get("tools"), source, seen)
    return {
        "summary": _clean_line(data.get("summary"), MAX_SUMMARY_CHARS),
        "responsibilities": _clean_bullets(data.get("responsibilities")),
        "qualifications": _clean_bullets(data.get("qualifications")),
        "skills_required": required,
        "skills_preferred": preferred,
        "tools": tools,
    }


def summarize_job_with_ai(title: str | None, description: str | None) -> dict[str, Any] | None:
    """
    Summary, responsibilities, qualifications, skills and tools for one posting (plus "_model").
    None when the call fails; raises AIQuotaExhausted when no provider has budget left.
    """
    description = (description or "").strip()
    if not description:
        return None
    if not ai_enrichment_enabled():
        raise AIQuotaExhausted("No AI provider is configured")
    max_tokens = int(_setting("AI_MAX_INPUT_TOKENS", str(DEFAULT_MAX_INPUT_TOKENS)))
    posting = trim_posting(description, max_tokens)
    prompt = _PROMPT.format(title=(title or "").strip(), description=posting)
    try:
        data, model = _generate(prompt)
    except AIQuotaExhausted:
        raise
    except Exception as e:
        logger.warning("AI job summary failed for %r: %s", title, e)
        return None
    result = validate_ai_result(data, posting, title or "")
    if result is not None:
        result["_model"] = model
    return result


# --- Storing on the job -----------------------------------------------------------------------

def _bullets(lines: list[str]) -> str | None:
    return "\n".join(f"• {ln}" for ln in lines) or None


AI_FIELDS = [
    "responsibilities", "qualifications", "structured_description",
    "skills_required", "skills_preferred", "tech_stack", "tech_stack_candidates", "embedding_text",
]


def _write_fields(job, result: dict[str, Any]) -> None:
    job.responsibilities = _bullets(result["responsibilities"]) or job.responsibilities
    job.qualifications = _bullets(result["qualifications"]) or job.qualifications
    job.skills_required = result["skills_required"]
    job.skills_preferred = result["skills_preferred"]
    job.tech_stack = sorted(
        set(result["skills_required"]) | set(result["skills_preferred"]) | set(result["tools"]),
        key=str.lower,
    )
    job.tech_stack_candidates = []
    sd = job.structured_description if isinstance(job.structured_description, dict) else {}
    if result["summary"]:
        sd["summary"] = result["summary"]
    job.structured_description = sd
    parts = [job.title or ""] + result["skills_required"] + result["skills_preferred"] + list(job.languages_required or [])
    job.embedding_text = " ".join(p for p in parts if p).strip() or None


def apply_ai_result(job, result: dict[str, Any]) -> None:
    """Write an AI result onto the job and remember it for later fetches (does not save)."""
    result = dict(result)
    model = result.pop("_model", None)
    sd = job.structured_description if isinstance(job.structured_description, dict) else {}
    sd["ai"] = {
        "fingerprint": description_fingerprint(job.title, job.description),
        "model": model,
        "version": AI_ENRICHMENT_VERSION,
        "enriched_at": timezone.now().isoformat(),
        "result": result,
    }
    job.structured_description = sd
    _write_fields(job, result)


def current_ai_result(job) -> dict[str, Any] | None:
    """The stored AI result if it was made from the job's current title and description."""
    sd = job.structured_description if isinstance(job.structured_description, dict) else {}
    ai = sd.get("ai") if isinstance(sd.get("ai"), dict) else None
    if not ai or not isinstance(ai.get("result"), dict):
        return None
    if ai.get("fingerprint") != description_fingerprint(job.title, job.description):
        return None
    return ai["result"]


def reapply_ai_fields(job) -> bool:
    """Restore AI fields after rule-based parsers overwrote them (does not save)."""
    result = current_ai_result(job)
    if result is None:
        return False
    _write_fields(job, result)
    return True
