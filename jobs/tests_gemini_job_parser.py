"""Tests for Gemini job parsing helpers (no live API calls)."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from jobs.gemini_job_parser import (
    is_employer_manual_job,
    parse_job_description_with_gemini,
    validate_and_normalize_parsed,
)


class ValidateNormalizeTests(TestCase):
    def test_limits_and_skill_sort(self):
        out = validate_and_normalize_parsed(
            {
                "responsibilities": ["a", "b", "c", "d", "e", "f", "g"],
                "qualifications": ["x"],
                "skills_required": ["Python", "AWS", "Python"],
            }
        )
        self.assertEqual(len(out["responsibilities"]), 7)
        self.assertEqual(out["qualifications"], ["x"])
        self.assertEqual(out["skills_required"], ["AWS", "Python"])

    def test_invalid_input_returns_empty(self):
        out = validate_and_normalize_parsed("not a dict")
        self.assertEqual(out["responsibilities"], [])
        assert out == {"responsibilities": [], "qualifications": [], "skills_required": []}


class IsEmployerManualTests(TestCase):
    def test_employer_manual_source(self):
        j = SimpleNamespace(platform="employer", raw={"source": "employer_manual"})
        self.assertTrue(is_employer_manual_job(j))

    def test_legacy_employer_source(self):
        j = SimpleNamespace(platform="employer", raw={"source": "employer"})
        self.assertTrue(is_employer_manual_job(j))

    def test_greenhouse_blocked(self):
        j = SimpleNamespace(platform="greenhouse", raw={"source": "imported"})
        self.assertFalse(is_employer_manual_job(j))


@override_settings(GEMINI_API_KEY="")
class ParseWithoutKeyTests(TestCase):
    def test_returns_empty_without_key(self):
        out = parse_job_description_with_gemini("We need Python and AWS developers.")
        self.assertEqual(out["skills_required"], [])


def _google_genai_installed() -> bool:
    try:
        import google.generativeai  # noqa: F401
    except ImportError:
        return False
    return True


@override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-2.0-flash")
class ParseWithMockGeminiTests(TestCase):
    @unittest.skipUnless(_google_genai_installed(), "google-generativeai not installed")
    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerationConfig", side_effect=lambda **kw: kw)
    @patch("google.generativeai.GenerativeModel")
    def test_parses_json_from_model(self, mock_gm, mock_gc, mock_configure):
        mock_resp = MagicMock()
        mock_resp.text = (
            '{"responsibilities":["განვითარება"],"qualifications":["გამოცდილება"],"skills_required":["Python"]}'
        )
        mock_gm.return_value.generate_content.return_value = mock_resp

        out = parse_job_description_with_gemini("Need Python developer.")

        self.assertEqual(out["responsibilities"], ["განვითარება"])
        self.assertEqual(out["qualifications"], ["გამოცდილება"])
        self.assertEqual(out["skills_required"], ["Python"])
