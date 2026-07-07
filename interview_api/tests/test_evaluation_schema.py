"""Unit tests for interview evaluation schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from interview_api.schemas.evaluation import InterviewEvaluationResult


def _valid_payload() -> dict:
    return {
        "overall_score": 82,
        "status": "PASSED",
        "requires_retake": False,
        "user_transcript": "მე ვმუშაობ Python-ზე და Django-ზე.",
        "metrics": {
            "technical_accuracy": {
                "score": 85,
                "label": "ტექნიკური სიზუსტე",
                "feedback": "კარგი ტექნიკური დეტალები.",
            },
            "structure_star": {
                "score": 78,
                "label": "პასუხის სტრუქტურა (STAR)",
                "feedback": "STAR სტრუქტურა ნაწილობრივ ჩანს.",
            },
            "delivery_confidence": {
                "score": 80,
                "label": "თვითპრეზენტაცია და ენა",
                "feedback": "გამოხატვა თავდაჯერებულია.",
            },
        },
        "strengths": ["კარგი ტექნიკური ბაზა"],
        "improvements": ["დაამატე კონკრეტული მაგალითები"],
        "missing_concepts": [],
        "recommended_answer": "იდეალური პასუხი ქართულად.",
    }


def test_valid_evaluation_parses():
    result = InterviewEvaluationResult.model_validate(_valid_payload())
    assert result.overall_score == 82
    assert result.status == "PASSED"
    assert result.requires_retake is False


def test_auto_corrects_status_and_retake_for_low_score():
    payload = _valid_payload()
    payload["overall_score"] = 60
    payload["status"] = "PASSED"
    payload["requires_retake"] = False

    result = InterviewEvaluationResult.model_validate(payload)
    assert result.status == "FAILED"
    assert result.requires_retake is True


def test_rejects_score_out_of_range():
    payload = _valid_payload()
    payload["overall_score"] = 150
    with pytest.raises(ValidationError):
        InterviewEvaluationResult.model_validate(payload)
