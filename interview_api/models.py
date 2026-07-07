import uuid

from django.db import models

from interview_api.storage import interview_audio_storage


class Interview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=255, db_index=True)
    job_position = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.job_position} ({self.id})"


class InterviewQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    interview = models.ForeignKey(
        Interview,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    question_text = models.TextField()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.question_text[:80]


class InterviewAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        InterviewQuestion,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    audio_file = models.FileField(
        upload_to="interview_records/",
        storage=interview_audio_storage,
    )
    transcript = models.TextField(blank=True, null=True)
    overall_score = models.IntegerField(default=0)
    metrics = models.JSONField(default=dict)
    strengths = models.JSONField(default=list)
    improvements = models.JSONField(default=list)
    missing_concepts = models.JSONField(default=list)
    recommended_answer = models.TextField(blank=True, default="")
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Attempt {self.id} (score={self.overall_score})"
