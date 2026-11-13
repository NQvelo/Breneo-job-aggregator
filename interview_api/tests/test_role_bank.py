"""Prepared interview roles stay aligned with the /start onboarding catalog."""

from django.test import SimpleTestCase

from interview_api.constants import QUESTIONS_PER_ROLE
from interview_api.question_bank import ROLE_QUESTIONS
from interview_api.role_catalog import INTERVIEW_ROLES, match_role_slug


class RoleBankTests(SimpleTestCase):
    def test_every_onboarding_role_has_ten_unique_questions(self):
        slugs = [slug for slug, _title, _title_ka in INTERVIEW_ROLES]
        self.assertEqual(len(slugs), 94)
        self.assertEqual(set(slugs), set(ROLE_QUESTIONS))
        for slug in slugs:
            questions = ROLE_QUESTIONS[slug]
            self.assertEqual(len(questions), QUESTIONS_PER_ROLE, slug)
            self.assertEqual(len(set(questions)), QUESTIONS_PER_ROLE, slug)
            for text in questions:
                self.assertGreater(len(text.strip()), 40, slug)

    def test_job_titles_map_to_onboarding_roles(self):
        self.assertEqual(match_role_slug("React Developer"), "react")
        self.assertEqual(match_role_slug("React დეველოპერი"), "react")
        self.assertEqual(match_role_slug("Frontend Developer"), "frontend")
        self.assertEqual(match_role_slug("Senior Python Developer"), "backend")
        self.assertEqual(match_role_slug("ბუღალტერი"), "accountant")
        self.assertEqual(match_role_slug("DevOps Engineer"), "devops")
        self.assertIsNone(match_role_slug("Astronaut"))
