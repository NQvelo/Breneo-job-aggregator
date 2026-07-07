"""Business logic for interview sessions, questions, and attempts."""

from __future__ import annotations

from django.db import transaction

from interview_api.exceptions import InterviewAPIError
from interview_api.models import Interview, InterviewAttempt, InterviewQuestion
from interview_api.schemas.evaluation import InterviewEvaluationResult
from interview_api.services.llm_service import evaluate_interview_answer, generate_interview_question
from interview_api.services.whisper_service import transcribe_audio


class InterviewService:
    @transaction.atomic
    def start_interview(self, *, user_id: str, job_position: str) -> tuple[Interview, InterviewQuestion]:
        interview = Interview.objects.create(
            user_id=user_id.strip(),
            job_position=job_position.strip(),
        )
        question_text = generate_interview_question(job_position)
        question = InterviewQuestion.objects.create(
            interview=interview,
            question_text=question_text,
        )
        return interview, question

    @transaction.atomic
    def submit_audio(
        self,
        *,
        question: InterviewQuestion,
        audio_file,
    ) -> InterviewEvaluationResult:
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
        return evaluation
