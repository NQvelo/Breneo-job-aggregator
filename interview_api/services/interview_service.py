"""Business logic for interview sessions, questions, and attempts."""

from __future__ import annotations

import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from django.db import transaction

from interview_api.constants import MAX_INTERVIEW_QUESTIONS
from interview_api.exceptions import InterviewAPIError, InterviewRoleNotFound, TTSServiceError
from interview_api.models import Interview, InterviewAttempt, InterviewQuestion, PreparedSpeech
from interview_api.role_matching import display_title_for_slug, resolve_interview_role
from interview_api.schemas.evaluation import InterviewEvaluationResult
from interview_api.services.job_context import InterviewJobContext
from interview_api.services.llm_service import evaluate_interview_answer
from interview_api.services.tts_service import synthesize_question_audio
from interview_api.services.welcome_service import build_welcome_text
from interview_api.services.whisper_service import transcribe_audio


@dataclass(frozen=True)
class SubmitAudioResult:
    evaluation: InterviewEvaluationResult
    question_number: int
    total_questions: int
    interview_complete: bool
    next_question: InterviewQuestion | None


class InterviewService:
    def _job_context(self, interview: Interview) -> InterviewJobContext:
        if interview.job_id and interview.job:
            return InterviewJobContext.from_job(interview.job)
        return InterviewJobContext.from_position(interview.job_position)

    def _session_length(self, interview: Interview) -> int:
        planned = interview.planned_questions or []
        if planned:
            return len(planned)
        return MAX_INTERVIEW_QUESTIONS

    @staticmethod
    def _speech_hash(text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def _stored_speech_name(self, text: str) -> str:
        existing = PreparedSpeech.objects.filter(text_hash=self._speech_hash(text)).first()
        if existing is not None and existing.audio and existing.audio.name:
            return existing.audio.name
        return ""

    def _store_speech(self, text: str, audio) -> str:
        digest = self._speech_hash(text)
        row, _created = PreparedSpeech.objects.get_or_create(text_hash=digest)
        if not row.audio or not row.audio.name:
            row.audio.save(f"{digest[:16]}.mp3", audio, save=True)
        return row.audio.name

    def _speech_name(self, text: str) -> str:
        """Reuse stored speech for this exact text. Synthesize only on a cache miss."""
        cached = self._stored_speech_name(text)
        if cached:
            return cached
        return self._store_speech(text, synthesize_question_audio(text.strip()))

    def _speech_names(self, welcome_text: str, question_text: str) -> tuple[str, str]:
        """Look up both clips, and synthesize any misses at the same time."""
        welcome_name = self._stored_speech_name(welcome_text)
        question_name = self._stored_speech_name(question_text)
        missing: list[tuple[str, str]] = []
        if not welcome_name:
            missing.append(("welcome", welcome_text.strip()))
        if not question_name:
            missing.append(("question", question_text.strip()))
        if not missing:
            return welcome_name, question_name

        with ThreadPoolExecutor(max_workers=len(missing)) as pool:
            synthesized = {
                key: pool.submit(synthesize_question_audio, text)
                for key, text in missing
            }
            audio_by_key = {key: future.result() for key, future in synthesized.items()}

        if not welcome_name:
            welcome_name = self._store_speech(welcome_text, audio_by_key["welcome"])
        if not question_name:
            question_name = self._store_speech(question_text, audio_by_key["question"])
        return welcome_name, question_name

    def _assign_cached_audio(self, file_field, text: str) -> None:
        file_field.name = self._speech_name(text)

    def _ensure_audio(self, question: InterviewQuestion) -> InterviewQuestion:
        if question.question_audio and question.question_audio.name:
            return question
        self._assign_cached_audio(question.question_audio, question.question_text)
        question.save(update_fields=["question_audio"])
        return question

    def _create_spoken_question(
        self,
        *,
        interview: Interview,
        order: int,
        question_text: str,
        with_audio: bool,
        audio_name: str = "",
    ) -> InterviewQuestion:
        question = InterviewQuestion(
            interview=interview,
            order=order,
            question_text=question_text,
        )
        if with_audio:
            question.question_audio.name = audio_name or self._speech_name(question_text)
        question.save()
        return question

    def _select_questions(self, role) -> list[str]:
        bank = list(role.questions.order_by("position").values_list("question_text", flat=True))
        if not bank:
            raise InterviewRoleNotFound("This role has no prepared interview questions.")
        count = min(MAX_INTERVIEW_QUESTIONS, len(bank))
        return random.sample(bank, count)

    def _next_question(
        self,
        interview: Interview,
        current_order: int,
        *,
        with_audio: bool = True,
    ) -> InterviewQuestion | None:
        existing = interview.questions.filter(order=current_order + 1).first()
        if existing is not None:
            return self._ensure_audio(existing) if with_audio else existing

        planned = list(interview.planned_questions or [])
        if current_order >= len(planned):
            return None
        return self._create_spoken_question(
            interview=interview,
            order=current_order + 1,
            question_text=planned[current_order],
            with_audio=with_audio,
        )

    def _welcome_for(self, *, job, position: str, question_count: int) -> str:
        if job is not None:
            context = InterviewJobContext.from_job(job)
        else:
            context = InterviewJobContext.from_position(position)
        return build_welcome_text(context, question_count=question_count)

    @transaction.atomic
    def start_interview(
        self,
        *,
        user_id: str,
        job_position: str,
        job=None,
        role_slug: str = "",
        spoken: bool = True,
    ) -> tuple[Interview, InterviewQuestion]:
        role = resolve_interview_role(
            role_slug=role_slug,
            job_position=job_position,
            job=job,
        )
        selected = self._select_questions(role)
        position = (job_position or "").strip() or display_title_for_slug(role.slug)
        welcome_text = self._welcome_for(
            job=job,
            position=position,
            question_count=len(selected),
        )
        welcome_name = ""
        first_audio_name = ""
        if spoken:
            # Speech for the welcome and the first bank question runs together.
            # Later questions stay text-only until the candidate reaches them.
            welcome_name, first_audio_name = self._speech_names(welcome_text, selected[0])
            if not welcome_name or not first_audio_name:
                raise TTSServiceError("Welcome audio could not be saved.")

        interview = Interview.objects.create(
            user_id=user_id.strip(),
            job=job,
            role=role,
            job_position=position,
            planned_questions=selected,
            welcome_text=welcome_text,
        )
        if welcome_name:
            interview.welcome_audio.name = welcome_name
            interview.save(update_fields=["welcome_audio"])
        first_question = None
        for order, question_text in enumerate(selected, start=1):
            question = self._create_spoken_question(
                interview=interview,
                order=order,
                question_text=question_text,
                with_audio=spoken and order == 1,
                audio_name=first_audio_name if spoken and order == 1 else "",
            )
            if order == 1:
                first_question = question
        if first_question is None:
            raise InterviewRoleNotFound("This role has no prepared interview questions.")
        interview = (
            Interview.objects.select_related("job", "job__company", "role")
            .prefetch_related("questions")
            .get(pk=interview.pk)
        )
        return interview, first_question

    @transaction.atomic
    def submit_audio(
        self,
        *,
        question: InterviewQuestion,
        audio_file,
    ) -> SubmitAudioResult:
        attempt = InterviewAttempt.objects.create(
            question=question,
            audio_file=audio_file,
            is_completed=False,
        )

        try:
            transcript = transcribe_audio(audio_file)
            evaluation = evaluate_interview_answer(question.question_text, transcript)
        except InterviewAPIError:
            attempt.delete()
            raise

        attempt.transcript = evaluation.user_transcript
        attempt.overall_score = evaluation.overall_score
        attempt.metrics = evaluation.metrics.model_dump()
        attempt.strengths = evaluation.strengths
        attempt.improvements = evaluation.improvements
        attempt.missing_concepts = evaluation.missing_concepts
        attempt.recommended_answer = evaluation.recommended_answer
        attempt.is_completed = True
        attempt.save(
            update_fields=[
                "transcript",
                "overall_score",
                "metrics",
                "strengths",
                "improvements",
                "missing_concepts",
                "recommended_answer",
                "is_completed",
            ]
        )

        interview = Interview.objects.select_related("job", "job__company", "role").get(
            pk=question.interview_id
        )
        question_number = question.order
        next_question = self._next_question(interview, question_number)

        return SubmitAudioResult(
            evaluation=evaluation,
            question_number=question_number,
            total_questions=self._session_length(interview),
            interview_complete=next_question is None,
            next_question=next_question,
        )

    @transaction.atomic
    def submit_text(self, *, question: InterviewQuestion, answer: str) -> SubmitAudioResult:
        text = answer.strip()
        if not text:
            raise InterviewAPIError("Answer text is required.", status_code=400)

        attempt = InterviewAttempt.objects.create(
            question=question,
            is_completed=False,
        )
        try:
            evaluation = evaluate_interview_answer(question.question_text, text)
        except InterviewAPIError:
            attempt.delete()
            raise

        attempt.transcript = evaluation.user_transcript
        attempt.overall_score = evaluation.overall_score
        attempt.metrics = evaluation.metrics.model_dump()
        attempt.strengths = evaluation.strengths
        attempt.improvements = evaluation.improvements
        attempt.missing_concepts = evaluation.missing_concepts
        attempt.recommended_answer = evaluation.recommended_answer
        attempt.is_completed = True
        attempt.save(
            update_fields=[
                "transcript",
                "overall_score",
                "metrics",
                "strengths",
                "improvements",
                "missing_concepts",
                "recommended_answer",
                "is_completed",
            ]
        )

        interview = Interview.objects.select_related("job", "job__company", "role").get(
            pk=question.interview_id
        )
        question_number = question.order
        next_question = self._next_question(
            interview,
            question_number,
            with_audio=False,
        )
        return SubmitAudioResult(
            evaluation=evaluation,
            question_number=question_number,
            total_questions=self._session_length(interview),
            interview_complete=next_question is None,
            next_question=next_question,
        )
