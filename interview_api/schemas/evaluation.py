"""Strict Pydantic models for LLM evaluation JSON validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class MetricScore(BaseModel):
    score: int = Field(ge=0, le=100)
    label: str
    feedback: str


class InterviewMetrics(BaseModel):
    technical_accuracy: MetricScore
    structure_star: MetricScore
    delivery_confidence: MetricScore


class InterviewEvaluationResult(BaseModel):
    """Enforces the rigid JSON schema returned by the evaluation LLM."""

    overall_score: int = Field(ge=0, le=100)
    status: Literal["PASSED", "FAILED"]
    requires_retake: bool
    user_transcript: str
    metrics: InterviewMetrics
    strengths: list[str] = Field(min_length=1)
    improvements: list[str] = Field(min_length=1)
    missing_concepts: list[str] = Field(default_factory=list)
    recommended_answer: str = Field(min_length=1)

    @model_validator(mode="after")
    def align_status_with_score(self) -> "InterviewEvaluationResult":
        passed = self.overall_score >= 75
        expected_status: Literal["PASSED", "FAILED"] = "PASSED" if passed else "FAILED"
        expected_retake = not passed
        object.__setattr__(self, "status", expected_status)
        object.__setattr__(self, "requires_retake", expected_retake)
        return self

    @field_validator("metrics", mode="before")
    @classmethod
    def ensure_metric_labels(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        labels = {
            "technical_accuracy": "ტექნიკური სიზუსტე",
            "structure_star": "პასუხის სტრუქტურა (STAR)",
            "delivery_confidence": "თვითპრეზენტაცია და ენა",
        }
        for key, label in labels.items():
            metric = value.get(key)
            if isinstance(metric, dict):
                metric["label"] = label
        return value
