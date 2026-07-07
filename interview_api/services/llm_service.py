"""LLM service for question generation and interview answer evaluation."""

from __future__ import annotations

import json
import logging
import os
import re

import requests
from django.conf import settings

from interview_api.exceptions import LLMResponseParseError, LLMServiceError
from interview_api.schemas.evaluation import InterviewEvaluationResult

logger = logging.getLogger(__name__)

QUESTION_SYSTEM_PROMPT = """You are an expert HR Technical Recruiter for the Breneo EdTech platform.
Generate exactly ONE highly relevant, role-specific behavioral or technical interview question.

Rules:
- The question must be in Georgian.
- Tailor difficulty and topic to the provided job_position.
- This is question {question_number} of {total_questions} in a single interview session.
- Vary topics across the session (technical depth, behavioral STAR, problem-solving, teamwork, etc.).
- Do NOT repeat or closely paraphrase any question listed in previous_questions.
- Return ONLY raw JSON: {{"question_text": "<Georgian question>"}}
- No markdown, no extra keys."""

EVALUATION_SYSTEM_PROMPT = """You are an expert HR Technical Recruiter. Analyze the user's transcript in Georgian based on Technical Accuracy, STAR structure, and Delivery Confidence. You must respond ONLY with a valid raw JSON object.

Evaluate based on:
1. Technical Accuracy (ტექნიკური სიზუსტე) — domain knowledge and factual correctness.
2. STAR Structure (პასუხის სტრუქტურა) — Situation, Task, Action, Result framing.
3. Delivery & Confidence (თვითპრეზენტაცია და ენა) — clarity, professionalism, and language quality.

You must respond ONLY with a valid JSON object matching this exact schema:
{schema}

Rules:
- overall_score is 0-100 (weighted: 40% technical, 35% STAR, 25% delivery).
- status is "PASSED" if overall_score >= 75, otherwise "FAILED".
- requires_retake is true when overall_score < 75.
- user_transcript must be the exact transcript provided (do not rewrite it).
- strengths, improvements, missing_concepts, and recommended_answer must be in Georgian.
- Metric labels must use the exact Georgian strings specified in the schema.
- Return ONLY raw JSON — no markdown fences, no commentary."""


def _strip_json_fence(text: str) -> str:
    stripped = (text or "").strip()
    match = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", stripped, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped


def _parse_json_response(raw_text: str) -> dict:
    cleaned = _strip_json_fence(raw_text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMResponseParseError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise LLMResponseParseError("LLM JSON response must be an object.")
    return payload


def _llm_settings() -> tuple[str, str, str]:
    provider = (
        os.environ.get("INTERVIEW_LLM_PROVIDER", "").strip().lower()
        or getattr(settings, "INTERVIEW_LLM_PROVIDER", "groq")
    ).lower()

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise LLMServiceError("OPENAI_API_KEY is not configured.")
        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o").strip()
        url = "https://api.openai.com/v1/chat/completions"
        return url, api_key, model

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise LLMServiceError("GROQ_API_KEY is not configured.")
    model = os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile").strip()
    url = "https://api.groq.com/openai/v1/chat/completions"
    return url, api_key, model


def _chat_completion(system_prompt: str, user_prompt: str) -> str:
    url, api_key, model = _llm_settings()
    timeout = int(os.environ.get("INTERVIEW_LLM_TIMEOUT_SECONDS", "90") or "90")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("LLM request failed")
        raise LLMServiceError(f"LLM request failed: {exc}") from exc

    if response.status_code >= 400:
        logger.error("LLM error %s: %s", response.status_code, response.text[:500])
        raise LLMServiceError(f"LLM API returned HTTP {response.status_code}.")

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMServiceError("Unexpected LLM response shape.") from exc


def generate_interview_question(
    job_position: str,
    *,
    question_number: int = 1,
    total_questions: int = 10,
    previous_questions: list[str] | None = None,
) -> str:
    previous = previous_questions or []
    previous_block = "\n".join(f"- {q}" for q in previous) if previous else "(none yet)"
    system_prompt = QUESTION_SYSTEM_PROMPT.format(
        question_number=question_number,
        total_questions=total_questions,
    )
    user_prompt = (
        f"job_position: {job_position.strip()}\n"
        f"question_number: {question_number}\n"
        f"total_questions: {total_questions}\n"
        f"previous_questions:\n{previous_block}"
    )
    raw = _chat_completion(system_prompt, user_prompt)
    payload = _parse_json_response(raw)
    question_text = (payload.get("question_text") or "").strip()
    if not question_text:
        raise LLMResponseParseError("LLM did not return question_text.")
    return question_text


def evaluate_interview_answer(question_text: str, transcript: str) -> InterviewEvaluationResult:
    schema = json.dumps(InterviewEvaluationResult.model_json_schema(), ensure_ascii=False)
    system_prompt = EVALUATION_SYSTEM_PROMPT.format(schema=schema)
    user_prompt = (
        f"Interview question:\n{question_text.strip()}\n\n"
        f"Candidate transcript (Georgian):\n{transcript.strip()}"
    )
    raw = _chat_completion(system_prompt, user_prompt)
    payload = _parse_json_response(raw)
    payload["user_transcript"] = transcript.strip()
    try:
        return InterviewEvaluationResult.model_validate(payload)
    except Exception as exc:
        raise LLMResponseParseError(f"Evaluation JSON failed validation: {exc}") from exc
