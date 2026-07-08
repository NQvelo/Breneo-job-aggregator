"""Business logic for interview sessions, questions, and attempts."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from interview_api.constants import MAX_INTERVIEW_QUESTIONS
from interview_api.exceptions import InterviewAPIError
from interview_api.models import Interview, InterviewAttempt, InterviewQuestion
from interview_api.schemas.evaluation import InterviewEvaluationResult
from interview_api.services.job_context import InterviewJobContext
from interview_api.services.llm_service import evaluate_interview_answer, generate_interview_question
from interview_api.services.tts_service import synthesize_question_audio
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

    def _create_question(
        self,
        *,
        interview: Interview,
        order: int,
        previous_questions: list[str],
    ) -> InterviewQuestion:
        question_text = generate_interview_question(
            self._job_context(interview),
            question_number=order,
            total_questions=MAX_INTERVIEW_QUESTIONS,
            previous_questions=previous_questions,
        )
        question = InterviewQuestion(
            interview=interview,
            order=order,
            question_text=question_text,
        )
        question.question_audio.save(
            f"interview_{interview.id}_q{order}.mp3",
            synthesize_question_audio(question_text),
            save=False,
        )
        question.save()
        return question

    @transaction.atomic
    def start_interview(
        self,
        *,
        user_id: str,
        job_position: str,
        job=None,
    ) -> tuple[Interview, InterviewQuestion]:
        interview = Interview.objects.create(
            user_id=user_id.strip(),
            job=job,
            job_position=job_position.strip(),
        )
        question = self._create_question(
            interview=interview,
            order=1,
            previous_questions=[],
        )
        return interview, question

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

        interview = Interview.objects.select_related("job", "job__company").get(
            pk=question.interview_id
        )
        question_number = question.order
        interview_complete = question_number >= MAX_INTERVIEW_QUESTIONS
        next_question = None

        if not interview_complete:
            previous_questions = list(
                interview.questions.order_by("order").values_list("question_text", flat=True)
            )
            next_question = self._create_question(
                interview=interview,
                order=question_number + 1,
                previous_questions=previous_questions,
            )

        return SubmitAudioResult(
            evaluation=evaluation,
            question_number=question_number,
            total_questions=MAX_INTERVIEW_QUESTIONS,
            interview_complete=interview_complete,
            next_question=next_question,
        )
