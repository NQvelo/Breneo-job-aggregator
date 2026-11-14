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
from interview_api.question_bank import ROLE_QUESTIONS
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
        bank = ROLE_QUESTIONS["backend"]
        chosen = list(reversed(bank[:MAX_INTERVIEW_QUESTIONS]))
        with (
            patch(
                "interview_api.services.interview_service.random.sample",
                return_value=chosen,
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
        self.assertEqual(response.data["interview"]["role"], "backend")
        self.assertEqual(response.data["question"]["question_text"], chosen[0])
        self.assertEqual(response.data["question"]["question_number"], 1)
        self.assertEqual(response.data["question"]["total_questions"], MAX_INTERVIEW_QUESTIONS)
        self.assertTrue(response.data["question"]["question_audio_url"])
        self.assertEqual(
            [item["question_text"] for item in response.data["questions"]],
            chosen,
        )
        self.assertEqual(len(response.data["questions"]), MAX_INTERVIEW_QUESTIONS)
        self.assertIsNone(response.data["questions"][1]["question_audio_url"])
        self.assertIn("5", response.data["welcome_text"])
        self.assertTrue(response.data["welcome_text"])
        self.assertIn("გამარჯობა", response.data["welcome_text"])
        self.assertTrue(response.data["welcome_audio_url"])
        self.assertEqual(len(response.data["playback"]), 2)
        self.assertEqual(response.data["playback"][0]["type"], "welcome")
        self.assertTrue(response.data["playback"][0]["audio_url"])
        self.assertEqual(response.data["playback"][1]["type"], "question")
        interview = Interview.objects.get(user_id=self.user_id, job_position="Python Developer")
        self.assertEqual(interview.planned_questions, chosen)
        self.assertEqual(interview.questions.count(), MAX_INTERVIEW_QUESTIONS)

    def test_start_interview_rejects_unknown_role(self):
        response = self.client.post(
            "/api/v1/interview/start/",
            {"job_position": "Astronaut"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Interview.objects.exists())

    def test_transcribe_audio_uses_requested_language(self):
        audio = BytesIO(b"fake-audio-bytes")
        audio.name = "answer.webm"

        with patch(
            "interview_api.views.transcribe_audio",
            return_value="გამარჯობა, ვმუშაობ React-ზე.",
        ) as transcribe:
            response = self.client.post(
                "/api/v1/interview/transcribe/",
                {"audio_file": audio, "language": "ka"},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["transcript"], "გამარჯობა, ვმუშაობ React-ზე.")
        self.assertEqual(transcribe.call_args.kwargs["language"], "ka")

    def test_start_interview_accepts_role_slug(self):
        with patch(
            "interview_api.services.interview_service.synthesize_question_audio",
            side_effect=_mock_tts,
        ):
            response = self.client.post(
                "/api/v1/interview/start/",
                {"role": "accountant"},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["interview"]["role"], "accountant")
        self.assertEqual(response.data["interview"]["job_position"], "Accountant")
        texts = {item["question_text"] for item in response.data["questions"]}
        self.assertTrue(texts <= set(ROLE_QUESTIONS["accountant"]))
        self.assertEqual(len(texts), MAX_INTERVIEW_QUESTIONS)

    def test_start_reuses_prepared_question_speech(self):
        bank = ROLE_QUESTIONS["react"]
        chosen = list(bank[:MAX_INTERVIEW_QUESTIONS])
        tts = patch(
            "interview_api.services.interview_service.synthesize_question_audio",
            side_effect=_mock_tts,
        )
        sample = patch(
            "interview_api.services.interview_service.random.sample",
            return_value=chosen,
        )
        with tts as synthesize, sample:
            first = self.client.post(
                "/api/v1/interview/start/",
                {"role": "react"},
                format="json",
            )
            first_calls = synthesize.call_count
            second = self.client.post(
                "/api/v1/interview/start/",
                {"role": "react"},
                format="json",
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data["question"]["question_text"], chosen[0])
        self.assertEqual(second.data["question"]["question_text"], chosen[0])
        self.assertEqual(
            [item["question_text"] for item in second.data["questions"]],
            chosen,
        )
        self.assertGreater(first_calls, 0)
        self.assertEqual(synthesize.call_count, first_calls)

    def test_submit_audio_returns_evaluation_and_next_question(self):
        planned = [
            "აღწერეთ თქვენი ბოლო პროექტი.",
            "რა არის REST API?",
            "მესამე კითხვა.",
            "მეოთხე კითხვა.",
            "მეხუთე კითხვა.",
        ]
        interview = Interview.objects.create(
            user_id=self.user_id,
            job_position="Backend Engineer",
            planned_questions=planned,
        )
        question = InterviewQuestion.objects.create(
            interview=interview,
            order=1,
            question_text=planned[0],
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

        with patch(
            "interview_api.services.interview_service.synthesize_question_audio",
            side_effect=_mock_tts,
        ):
            response = self.client.post(
                "/api/v1/interview/start/",
                {"job_id": job.id},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["interview"]["job_id"], job.id)
        self.assertEqual(response.data["interview"]["job_position"], "Senior Python Developer")
        self.assertEqual(response.data["interview"]["role"], "backend")
        self.assertIn(
            response.data["question"]["question_text"],
            ROLE_QUESTIONS["backend"],
        )

    def test_start_text_interview_skips_speech(self):
        with (
            patch(
                "interview_api.services.interview_service.random.sample",
                return_value=list(reversed(ROLE_QUESTIONS["react"][:MAX_INTERVIEW_QUESTIONS])),
            ),
            patch(
                "interview_api.services.interview_service.synthesize_question_audio",
                side_effect=_mock_tts,
            ) as synthesize,
        ):
            response = self.client.post(
                "/api/v1/interview/start/",
                {"role": "react", "mode": "text"},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        synthesize.assert_not_called()
        self.assertIsNone(response.data["welcome_audio_url"])
        self.assertIsNone(response.data["question"]["question_audio_url"])
        self.assertFalse(response.data["playback"][0]["audio_url"])
        self.assertGreaterEqual(len(response.data["questions"]), 1)

    def test_submit_text_reviews_answer_without_audio(self):
        planned = [
            "აღწერეთ თქვენი ბოლო პროექტი.",
            "რა არის REST API?",
        ]
        interview = Interview.objects.create(
            user_id=self.user_id,
            job_position="React Developer",
            planned_questions=planned,
        )
        question = InterviewQuestion.objects.create(
            interview=interview,
            order=1,
            question_text=planned[0],
        )
        evaluation = InterviewEvaluationResult.model_validate(
            {
                "overall_score": 80,
                "status": "PASSED",
                "requires_retake": False,
                "user_transcript": "ვწერდი React კომპონენტებს.",
                "metrics": {
                    "technical_accuracy": {
                        "score": 80,
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
                "strengths": ["კონკრეტული მაგალითი"],
                "improvements": ["დაამატე შედეგი"],
                "missing_concepts": [],
                "recommended_answer": "უფრო სრული პასუხი.",
            }
        )
        with (
            patch(
                "interview_api.services.interview_service.evaluate_interview_answer",
                return_value=evaluation,
            ) as evaluate,
            patch(
                "interview_api.services.interview_service.synthesize_question_audio",
                side_effect=_mock_tts,
            ) as synthesize,
        ):
            response = self.client.post(
                f"/api/v1/interview/submit-text/{question.id}/",
                {"answer": "ვწერდი React კომპონენტებს."},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        evaluate.assert_called_once_with(planned[0], "ვწერდი React კომპონენტებს.")
        synthesize.assert_not_called()
        self.assertEqual(response.data["overall_score"], 80)
        self.assertEqual(response.data["user_transcript"], "ვწერდი React კომპონენტებს.")
        self.assertFalse(response.data["interview_complete"])
        self.assertEqual(response.data["next_question"]["question_text"], planned[1])
        self.assertIsNone(response.data["next_question"]["question_audio_url"])
        attempt = question.attempts.get()
        self.assertFalse(attempt.audio_file)
        self.assertTrue(attempt.is_completed)

    @patch.dict("os.environ", {"EMPLOYER_POST_SECRET": "test-bff-secret"})
    def test_start_interview_via_bff_auth(self):
        with patch(
            "interview_api.services.interview_service.synthesize_question_audio",
            side_effect=_mock_tts,
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
        with patch(
            "interview_api.services.interview_service.synthesize_question_audio",
            side_effect=_mock_tts,
        ):
            response = self.client.post(
                "/api/v1/interview/start/",
                {"job_position": "Backend Engineer", "user_id": self.user_id},
                format="json",
                HTTP_AUTHORIZATION="Bearer test-bff-secret",
            )

        self.assertEqual(response.status_code, 201)
