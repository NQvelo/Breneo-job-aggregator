"""API tests for mock interview endpoints."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase
from rest_framework.test import APIClient

from jobs.authentication.breneo_auth import BreneoUser
from interview_api.constants import MAX_INTERVIEW_QUESTIONS
from interview_api.models import Interview, InterviewQuestion
from interview_api.schemas.evaluation import InterviewEvaluationResult


def _mock_tts(_text: str) -> ContentFile:
    return ContentFile(b"fake-tts-mp3", name="question.mp3")


class InterviewAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_id = "test-user-1"
        self.breneo_user = BreneoUser(id=self.user_id)
        self.client.force_authenticate(user=self.breneo_user)

    def test_start_interview_creates_records(self):
        with (
            patch(
                "interview_api.services.interview_service.generate_interview_question",
                return_value="როგორ მუშაობთ Django-ზე?",
            ),
            patch(
                "interview_api.services.interview_service.synthesize_question_audio",
                side_effect=_mock_tts,
            ),
        ):
            response = self.client.post(
                "/api/v1/interview/start/",
                {"job_position": "Python Developer"},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["question"]["question_text"],
            "როგორ მუშაობთ Django-ზე?",
        )
        self.assertEqual(response.data["question"]["question_number"], 1)
        self.assertEqual(response.data["question"]["total_questions"], MAX_INTERVIEW_QUESTIONS)
        self.assertTrue(response.data["question"]["question_audio_url"])
        self.assertTrue(
            Interview.objects.filter(
                user_id=self.user_id,
                job_position="Python Developer",
            ).exists()
        )

    def test_submit_audio_returns_evaluation_and_next_question(self):
        interview = Interview.objects.create(
            user_id=self.user_id,
            job_position="Backend Engineer",
        )
        question = InterviewQuestion.objects.create(
            interview=interview,
            order=1,
            question_text="აღწერეთ თქვენი ბოლო პროექტი.",
        )

        evaluation = InterviewEvaluationResult.model_validate(
            {
                "overall_score": 82,
                "status": "PASSED",
                "requires_retake": False,
                "user_transcript": "ვმუშაობ Django-ზე.",
                "metrics": {
                    "technical_accuracy": {
                        "score": 85,
                        "label": "ტექნიკური სიზუსტე",
                        "feedback": "კარგი.",
                    },
                    "structure_star": {
                        "score": 78,
                        "label": "პასუხის სტრუქტურა (STAR)",
                        "feedback": "საშუალო.",
                    },
                    "delivery_confidence": {
                        "score": 80,
                        "label": "თვითპრეზენტაცია და ენა",
                        "feedback": "კარგი.",
                    },
                },
                "strengths": ["ტექნიკური ბაზა"],
                "improvements": ["მაგალითები"],
                "missing_concepts": [],
                "recommended_answer": "იდეალური პასუხი.",
            }
        )

        audio = BytesIO(b"fake-audio-bytes")
        audio.name = "answer.webm"

        with (
            patch(
                "interview_api.services.interview_service.transcribe_audio",
                return_value="ვმუშაობ Django-ზე.",
            ),
            patch(
                "interview_api.services.interview_service.evaluate_interview_answer",
                return_value=evaluation,
            ),
            patch(
                "interview_api.services.interview_service.generate_interview_question",
                return_value="რა არის REST API?",
            ),
            patch(
                "interview_api.services.interview_service.synthesize_question_audio",
                side_effect=_mock_tts,
            ),
        ):
            response = self.client.post(
                f"/api/v1/interview/submit-audio/{question.id}/",
                {"audio_file": audio},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["overall_score"], 82)
        self.assertEqual(response.data["status"], "PASSED")
        self.assertEqual(response.data["user_transcript"], "ვმუშაობ Django-ზე.")
        self.assertEqual(response.data["question_number"], 1)
        self.assertEqual(response.data["total_questions"], MAX_INTERVIEW_QUESTIONS)
        self.assertFalse(response.data["interview_complete"])
        self.assertIsNotNone(response.data["next_question"])
        self.assertEqual(response.data["next_question"]["question_number"], 2)
        self.assertEqual(response.data["next_question"]["question_text"], "რა არის REST API?")
        self.assertTrue(response.data["next_question"]["question_audio_url"])

    def test_submit_audio_completes_interview_on_last_question(self):
        interview = Interview.objects.create(
            user_id=self.user_id,
            job_position="Backend Engineer",
        )
        question = InterviewQuestion.objects.create(
            interview=interview,
            order=MAX_INTERVIEW_QUESTIONS,
            question_text="ბოლო კითხვა.",
        )

        evaluation = InterviewEvaluationResult.model_validate(
            {
                "overall_score": 90,
                "status": "PASSED",
                "requires_retake": False,
                "user_transcript": "პასუხი.",
                "metrics": {
                    "technical_accuracy": {
                        "score": 90,
                        "label": "ტექნიკური სიზუსტე",
                        "feedback": "კარგი.",
                    },
                    "structure_star": {
                        "score": 90,
                        "label": "პასუხის სტრუქტურა (STAR)",
                        "feedback": "კარგი.",
                    },
                    "delivery_confidence": {
                        "score": 90,
                        "label": "თვითპრეზენტაცია და ენა",
                        "feedback": "კარგი.",
                    },
                },
                "strengths": ["სიზუსტე"],
                "improvements": ["დეტალები"],
                "missing_concepts": [],
                "recommended_answer": "იდეალური პასუხი.",
            }
        )

        audio = BytesIO(b"fake-audio-bytes")
        audio.name = "answer.webm"

        with (
            patch(
                "interview_api.services.interview_service.transcribe_audio",
                return_value="პასუხი.",
            ),
            patch(
                "interview_api.services.interview_service.evaluate_interview_answer",
                return_value=evaluation,
            ),
        ):
            response = self.client.post(
                f"/api/v1/interview/submit-audio/{question.id}/",
                {"audio_file": audio},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["interview_complete"])
        self.assertIsNone(response.data["next_question"])
        self.assertEqual(interview.questions.count(), 1)

    def test_submit_audio_returns_400_on_cloudinary_rejection(self):
        from cloudinary.exceptions import BadRequest as CloudinaryBadRequest

        interview = Interview.objects.create(
            user_id=self.user_id,
            job_position="Backend Engineer",
        )
        question = InterviewQuestion.objects.create(
            interview=interview,
            order=1,
            question_text="აღწერეთ თქვენი ბოლო პროექტი.",
        )

        audio = BytesIO(b"fake-audio-bytes")
        audio.name = "answer.webm"

        with patch(
            "interview_api.views.InterviewService.submit_audio",
            side_effect=CloudinaryBadRequest("Invalid image file"),
        ):
            response = self.client.post(
                f"/api/v1/interview/submit-audio/{question.id}/",
                {"audio_file": audio},
                format="multipart",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Audio upload failed", response.data["detail"])

    def test_submit_audio_requires_auth(self):
        interview = Interview.objects.create(user_id="other-user", job_position="Role")
        question = InterviewQuestion.objects.create(
            interview=interview,
            order=1,
            question_text="Q?",
        )
        audio = BytesIO(b"x")
        audio.name = "a.webm"

        unauthenticated = APIClient()
        response = unauthenticated.post(
            f"/api/v1/interview/submit-audio/{question.id}/",
            {"audio_file": audio},
            format="multipart",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_start_interview_with_job_id_uses_job_context(self):
        from jobs.models import Company, Job

        company = Company.objects.create(name="Breneo Tech")
        job = Job.objects.create(
            title="Senior Python Developer",
            company=company,
            platform="test",
            external_job_id="py-1",
            skills_required=["Python", "Django"],
            qualifications="5+ years Python experience.",
        )

        with (
            patch(
                "interview_api.services.interview_service.generate_interview_question",
                return_value="როგორ მუშაობთ Django-ზე?",
            ) as mock_generate,
            patch(
                "interview_api.services.interview_service.synthesize_question_audio",
                side_effect=_mock_tts,
            ),
        ):
            response = self.client.post(
                "/api/v1/interview/start/",
                {"job_id": job.id},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["interview"]["job_id"], job.id)
        self.assertEqual(response.data["interview"]["job_position"], "Senior Python Developer")
        job_context = mock_generate.call_args.args[0]
        self.assertEqual(job_context.job_position, "Senior Python Developer")
        self.assertIn("Python", job_context.skills_required)

    @patch.dict("os.environ", {"EMPLOYER_POST_SECRET": "test-bff-secret"})
    def test_start_interview_via_bff_auth(self):
        with (
            patch(
                "interview_api.services.interview_service.generate_interview_question",
                return_value="კითხვა",
            ),
            patch(
                "interview_api.services.interview_service.synthesize_question_audio",
                side_effect=_mock_tts,
            ),
        ):
            response = self.client.post(
                "/api/v1/interview/start/",
                {"job_position": "DevOps Engineer", "user_id": self.user_id},
                format="json",
                HTTP_X_EMPLOYER_KEY="test-bff-secret",
            )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Interview.objects.filter(
                user_id=self.user_id,
                job_position="DevOps Engineer",
            ).exists()
        )

    @patch.dict("os.environ", {"EMPLOYER_POST_SECRET": "test-bff-secret"})
    def test_start_interview_via_bff_bearer_legacy(self):
        with (
            patch(
                "interview_api.services.interview_service.generate_interview_question",
                return_value="კითხვა",
            ),
            patch(
                "interview_api.services.interview_service.synthesize_question_audio",
                side_effect=_mock_tts,
            ),
        ):
            response = self.client.post(
                "/api/v1/interview/start/",
                {"job_position": "Backend Engineer", "user_id": self.user_id},
                format="json",
                HTTP_AUTHORIZATION="Bearer test-bff-secret",
            )

        self.assertEqual(response.status_code, 201)
