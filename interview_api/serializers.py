from __future__ import annotations

import mimetypes
from pathlib import Path

from rest_framework import serializers

from interview_api.models import Interview, InterviewAttempt, InterviewQuestion

MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".webm", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".ogg", ".oga"}


class StartInterviewSerializer(serializers.Serializer):
    job_position = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_job_position(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("job_position is required.")
        return cleaned


class InterviewQuestionSerializer(serializers.ModelSerializer):
    interview_id = serializers.UUIDField(source="interview.id", read_only=True)
    job_position = serializers.CharField(source="interview.job_position", read_only=True)

    class Meta:
        model = InterviewQuestion
        fields = ("id", "interview_id", "job_position", "question_text")


class InterviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interview
        fields = ("id", "job_position", "created_at")


class StartInterviewResponseSerializer(serializers.Serializer):
    interview = InterviewSerializer()
    question = InterviewQuestionSerializer()


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
