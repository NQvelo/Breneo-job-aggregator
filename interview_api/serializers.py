from __future__ import annotations

import mimetypes
from pathlib import Path

from rest_framework import serializers

from interview_api.constants import MAX_INTERVIEW_QUESTIONS
from interview_api.models import Interview, InterviewAttempt, InterviewQuestion
from jobs.models import Job

MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".webm", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".ogg", ".oga"}


def _absolute_file_url(file_field, request) -> str | None:
    if not file_field or not getattr(file_field, "name", ""):
        return None
    url = file_field.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


class StartInterviewSerializer(serializers.Serializer):
    job_position = serializers.CharField(max_length=255, trim_whitespace=True, required=False, allow_blank=True)
    job_id = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        job_id = attrs.get("job_id")
        job_position = (attrs.get("job_position") or "").strip()

        if job_id is not None:
            try:
                job = Job.objects.select_related("company").get(pk=job_id, is_active=True)
            except Job.DoesNotExist as exc:
                raise serializers.ValidationError({"job_id": "Job not found or inactive."}) from exc
            attrs["job"] = job
            attrs["job_position"] = job.title.strip()
            return attrs

        if not job_position:
            raise serializers.ValidationError(
                {"job_position": "job_position or job_id is required."}
            )
        attrs["job_position"] = job_position
        attrs["job"] = None
        return attrs


class InterviewQuestionSerializer(serializers.ModelSerializer):
    interview_id = serializers.UUIDField(source="interview.id", read_only=True)
    job_position = serializers.CharField(source="interview.job_position", read_only=True)
    question_number = serializers.IntegerField(source="order", read_only=True)
    total_questions = serializers.SerializerMethodField()
    question_audio_url = serializers.SerializerMethodField()

    class Meta:
        model = InterviewQuestion
        fields = (
            "id",
            "interview_id",
            "job_position",
            "question_text",
            "question_number",
            "total_questions",
            "question_audio_url",
        )

    def get_total_questions(self, obj) -> int:
        return MAX_INTERVIEW_QUESTIONS

    def get_question_audio_url(self, obj) -> str | None:
        return _absolute_file_url(obj.question_audio, self.context.get("request"))


class InterviewSerializer(serializers.ModelSerializer):
    job_id = serializers.IntegerField(source="job.id", read_only=True, allow_null=True)

    class Meta:
        model = Interview
        fields = ("id", "job_id", "job_position", "created_at")


class InterviewPlaybackItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["welcome", "question"])
    text = serializers.CharField()
    audio_url = serializers.CharField(allow_null=True)


class StartInterviewResponseSerializer(serializers.Serializer):
    interview = InterviewSerializer()
    welcome_text = serializers.SerializerMethodField()
    welcome_audio_url = serializers.SerializerMethodField()
    playback = serializers.SerializerMethodField()
    question = InterviewQuestionSerializer()

    def get_welcome_text(self, obj) -> str:
        return obj["interview"].welcome_text or ""

    def get_welcome_audio_url(self, obj) -> str | None:
        return _absolute_file_url(obj["interview"].welcome_audio, self.context.get("request"))

    def get_playback(self, obj) -> list[dict]:
        request = self.context.get("request")
        interview = obj["interview"]
        question = obj["question"]
        items = [
            {
                "type": "welcome",
                "text": interview.welcome_text or "",
                "audio_url": _absolute_file_url(interview.welcome_audio, request),
            },
            {
                "type": "question",
                "text": question.question_text,
                "audio_url": _absolute_file_url(question.question_audio, request),
            },
        ]
        return InterviewPlaybackItemSerializer(items, many=True).data


class SubmitAudioSerializer(serializers.Serializer):
    audio_file = serializers.FileField(required=False, allow_empty_file=False)
    audio = serializers.FileField(required=False, allow_empty_file=False)

    def validate(self, attrs):
        uploaded = attrs.get("audio_file") or attrs.get("audio")
        if uploaded is None:
            raise serializers.ValidationError(
                {"audio_file": "An audio or video file is required (audio_file or audio)."}
            )

        if uploaded.size > MAX_AUDIO_BYTES:
            raise serializers.ValidationError(
                {"audio_file": f"File exceeds maximum size of {MAX_AUDIO_BYTES // (1024 * 1024)} MB."}
            )

        if uploaded.size == 0:
            raise serializers.ValidationError({"audio_file": "Uploaded file is empty."})

        content_type = (getattr(uploaded, "content_type", "") or "").lower()
        extension = Path(getattr(uploaded, "name", "") or "").suffix.lower()
        is_audio_or_video = content_type.startswith("audio/") or content_type.startswith("video/")
        if not is_audio_or_video and extension not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                {
                    "audio_file": (
                        "Unsupported file type. Upload a common audio/video format "
                        "(webm, mp3, mp4, wav, m4a, ogg)."
                    )
                }
            )

        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(uploaded.name or "")
            if guessed:
                uploaded.content_type = guessed

        attrs["uploaded_file"] = uploaded
        return attrs


class InterviewAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewAttempt
        fields = (
            "id",
            "question",
            "transcript",
            "overall_score",
            "metrics",
            "strengths",
            "improvements",
            "missing_concepts",
            "recommended_answer",
            "is_completed",
            "created_at",
        )
        read_only_fields = fields


class InterviewEvaluationResponseSerializer(serializers.Serializer):
    overall_score = serializers.IntegerField(min_value=0, max_value=100)
    status = serializers.ChoiceField(choices=["PASSED", "FAILED"])
    requires_retake = serializers.BooleanField()
    user_transcript = serializers.CharField()
    metrics = serializers.DictField()
    strengths = serializers.ListField(child=serializers.CharField())
    improvements = serializers.ListField(child=serializers.CharField())
    missing_concepts = serializers.ListField(child=serializers.CharField())
    recommended_answer = serializers.CharField()

    @classmethod
    def from_evaluation(cls, evaluation) -> dict:
        return {
            "overall_score": evaluation.overall_score,
            "status": evaluation.status,
            "requires_retake": evaluation.requires_retake,
            "user_transcript": evaluation.user_transcript,
            "metrics": evaluation.metrics.model_dump(),
            "strengths": evaluation.strengths,
            "improvements": evaluation.improvements,
            "missing_concepts": evaluation.missing_concepts,
            "recommended_answer": evaluation.recommended_answer,
        }


class SubmitInterviewResponseSerializer(InterviewEvaluationResponseSerializer):
    question_number = serializers.IntegerField(min_value=1)
    total_questions = serializers.IntegerField(min_value=1)
    interview_complete = serializers.BooleanField()
    next_question = InterviewQuestionSerializer(allow_null=True)

    @classmethod
    def from_submit_result(cls, result, *, context=None) -> dict:
        payload = cls.from_evaluation(result.evaluation)
        payload.update(
            {
                "question_number": result.question_number,
                "total_questions": result.total_questions,
                "interview_complete": result.interview_complete,
                "next_question": (
                    InterviewQuestionSerializer(result.next_question, context=context or {}).data
                    if result.next_question is not None
                    else None
                ),
            }
        )
        return payload
