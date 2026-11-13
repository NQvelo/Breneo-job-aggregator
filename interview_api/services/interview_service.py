"""Business logic for interview sessions, questions, and attempts."""

from __future__ import annotations

import random
from dataclasses import dataclass

from django.db import transaction

from interview_api.constants import MAX_INTERVIEW_QUESTIONS
from interview_api.exceptions import InterviewAPIError, InterviewRoleNotFound, TTSServiceError
from interview_api.models import Interview, InterviewAttempt, InterviewQuestion
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

    def _ensure_audio(self, question: InterviewQuestion) -> InterviewQuestion:
        if question.question_audio and question.question_audio.name:
            return question
        question.question_audio.save(
            f"interview_{question.interview_id}_q{question.order}.mp3",
            synthesize_question_audio(question.question_text),
            save=False,
        )
        question.save(update_fields=["question_audio"])
        return question

    def _create_spoken_question(
        self,
        *,
        interview: Interview,
        order: int,
        question_text: str,
        with_audio: bool,
    ) -> InterviewQuestion:
        question = InterviewQuestion(
            interview=interview,
            order=order,
            question_text=question_text,
        )
        if with_audio:
            question.question_audio.save(
                f"interview_{interview.id}_q{order}.mp3",
                synthesize_question_audio(question_text),
                save=False,
            )
        question.save()
        return question

    def _select_questions(self, role) -> list[str]:
        bank = list(role.questions.order_by("position").values_list("question_text", flat=True))
        if not bank:
            raise InterviewRoleNotFound("This role has no prepared interview questions.")
        count = min(MAX_INTERVIEW_QUESTIONS, len(bank))
        return random.sample(bank, count)

    def _next_question(self, interview: Interview, current_order: int) -> InterviewQuestion | None:
        existing = interview.questions.filter(order=current_order + 1).first()
        if existing is not None:
            return self._ensure_audio(existing)

        planned = list(interview.planned_questions or [])
        if current_order >= len(planned):
            return None
        return self._create_spoken_question(
            interview=interview,
            order=current_order + 1,
            question_text=planned[current_order],
            with_audio=True,
        )

    def _attach_welcome(self, interview: Interview) -> None:
        if interview.job_id:
            interview = Interview.objects.select_related("job", "job__company").get(pk=interview.pk)

        context = self._job_context(interview)
        welcome_text = build_welcome_text(context, question_count=self._session_length(interview))
        interview.welcome_text = welcome_text
        interview.welcome_audio.save(
            f"interview_{interview.id}_welcome.mp3",
            synthesize_question_audio(welcome_text),
            save=False,
        )
        interview.save(update_fields=["welcome_text", "welcome_audio"])

        if not interview.welcome_audio.name:
            raise TTSServiceError("Welcome audio could not be saved.")

    @transaction.atomic
    def start_interview(
        self,
        *,
        user_id: str,
        job_position: str,
        job=None,
        role_slug: str = "",
    ) -> tuple[Interview, InterviewQuestion]:
        role = resolve_interview_role(
            role_slug=role_slug,
            job_position=job_position,
            job=job,
        )
        selected = self._select_questions(role)
        position = (job_position or "").strip() or display_title_for_slug(role.slug)
        interview = Interview.objects.create(
            user_id=user_id.strip(),
            job=job,
            role=role,
            job_position=position,
            planned_questions=selected,
        )
        self._attach_welcome(interview)
        first_question = None
        for order, question_text in enumerate(selected, start=1):
            question = self._create_spoken_question(
                interview=interview,
                order=order,
                question_text=question_text,
                with_audio=order == 1,
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
