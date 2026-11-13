"""AI job summaries (Gemini mocked; no live API calls)."""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from . import ai_job_enrichment as ai
from .models import Company, Job

DESCRIPTION = """About us
Acme builds the AI orchestration platform. Our customers use Illustrator, Notion and GitHub with us.

What you'll do
- Build and maintain backend services in Python
- Design PostgreSQL schemas
- Review code

Requirements
- 5+ years of backend experience
- Strong Python and postgres skills
Nice to have: Kubernetes
We track work in Jira.
"""

MODEL_OUTPUT = {
    "summary": "Senior backend role building Acme's core services.",
    "responsibilities": ["Build and maintain backend services in Python", "Design PostgreSQL schemas",
                         "• Review code", "Review code"],
    "qualifications": ["5+ years of backend experience"],
    "skills_required": [
        {"name": "Python", "evidence": "Strong Python"},
        {"name": "postgres", "evidence": "postgres skills"},
        {"name": "Django", "evidence": "Django REST framework"},  # not in the posting
    ],
    "skills_preferred": [{"name": "Kubernetes", "evidence": "Nice to have: Kubernetes"},
                         {"name": "Python", "evidence": "Python"}],
    "tools": [{"name": "Jira", "evidence": "work in Jira"}],
}


def _gemini_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
    return resp


class ValidateResultTests(SimpleTestCase):
    def test_keeps_only_quoted_skills_and_uses_catalog_names(self):
        out = ai.validate_ai_result(MODEL_OUTPUT, DESCRIPTION, "Senior Backend Engineer")
        self.assertEqual(out["skills_required"], ["PostgreSQL", "Python"])
        self.assertEqual(out["skills_preferred"], ["Kubernetes"])  # Python already required
        self.assertEqual(out["tools"], ["Jira"])
        self.assertEqual(out["responsibilities"], [
            "Build and maintain backend services in Python", "Design PostgreSQL schemas", "Review code",
        ])

    def test_georgian_evidence_is_accepted(self):
        data = {"summary": "", "responsibilities": [], "qualifications": [],
                "skills_required": [{"name": "Python", "evidence": "პითონის ცოდნა"}],
                "skills_preferred": [], "tools": [{"name": "Microsoft Excel", "evidence": "ექსელი"}]}
        out = ai.validate_ai_result(data, "მოთხოვნები: პითონის ცოდნა, ექსელი", "დეველოპერი")
        self.assertEqual(out["skills_required"], ["Python"])
        self.assertEqual(out["tools"], ["Microsoft Excel"])

    def test_bullets_are_capped(self):
        data = {"responsibilities": [f"Duty {i}" for i in range(20)]}
        out = ai.validate_ai_result(data, "text")
        self.assertEqual(len(out["responsibilities"]), ai.MAX_BULLETS)

    def test_non_dict_is_rejected(self):
        self.assertIsNone(ai.validate_ai_result("oops", "text"))


def _groq_response(payload, tokens=2000):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}],
        "usage": {"total_tokens": tokens},
    }
    return resp


def _rate_limited(message, retry_after="0"):
    resp = MagicMock()
    resp.status_code = 429
    resp.text = json.dumps({"error": {"message": message}})
    resp.headers = {"retry-after": retry_after}
    return resp


class _ProviderTestMixin:
    def setUp(self):
        ai.reset_provider_state()
        sleep = patch.object(ai.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)


@override_settings(GROQ_API_KEY="", GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-test")
class GeminiOnlyTests(_ProviderTestMixin, SimpleTestCase):
    def test_calls_gemini_with_schema_and_validates(self):
        with patch.object(ai.httpx, "post", return_value=_gemini_response(MODEL_OUTPUT)) as post:
            out = ai.summarize_job_with_ai("Senior Backend Engineer", DESCRIPTION)
        self.assertIn("gemini-test:generateContent", post.call_args.args[0])
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["generationConfig"]["responseSchema"], ai.GEMINI_RESPONSE_SCHEMA)
        self.assertNotIn("Django", out["skills_required"])
        self.assertEqual(out["summary"], MODEL_OUTPUT["summary"])
        self.assertEqual(out["_model"], "gemini:gemini-test")

    def test_api_error_returns_none(self):
        resp = MagicMock(status_code=403)
        resp.raise_for_status.side_effect = Exception("403 leaked key")
        with patch.object(ai.httpx, "post", return_value=resp):
            self.assertIsNone(ai.summarize_job_with_ai("Engineer", DESCRIPTION))

    @override_settings(GEMINI_API_KEY="")
    def test_no_key_raises_without_request(self):
        with patch.object(ai.httpx, "post") as post:
            with self.assertRaises(ai.AIQuotaExhausted):
                ai.summarize_job_with_ai("Engineer", DESCRIPTION)
        post.assert_not_called()


@override_settings(GROQ_API_KEY="groq-key", GEMINI_API_KEY="", GROQ_ENRICHMENT_MODELS="m1,m2")
class GroqTests(_ProviderTestMixin, SimpleTestCase):
    def test_uses_first_groq_model_in_json_mode(self):
        with patch.object(ai.httpx, "post", return_value=_groq_response(MODEL_OUTPUT)) as post:
            out = ai.summarize_job_with_ai("Senior Backend Engineer", DESCRIPTION)
        self.assertEqual(post.call_args.args[0], ai.GROQ_CHAT_URL)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "m1")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(out["_model"], "groq:m1")
        self.assertEqual(out["skills_required"], ["PostgreSQL", "Python"])

    def test_daily_limit_moves_to_next_model(self):
        daily = _rate_limited("Rate limit reached for model `m1` on tokens per day (TPD): Limit 200000")
        with patch.object(ai.httpx, "post", side_effect=[daily, _groq_response(MODEL_OUTPUT)]) as post:
            out = ai.summarize_job_with_ai("Engineer", DESCRIPTION)
            self.assertEqual(out["_model"], "groq:m2")
            self.assertEqual(post.call_args.kwargs["json"]["model"], "m2")
            # m1 stays out for the rest of the run
            post.side_effect = [_groq_response(MODEL_OUTPUT)]
            ai.summarize_job_with_ai("Engineer", DESCRIPTION)
            self.assertEqual(post.call_args.kwargs["json"]["model"], "m2")

    def test_minute_limit_waits_and_retries_same_model(self):
        minute = _rate_limited("Rate limit reached on tokens per minute (TPM)", retry_after="3")
        with patch.object(ai.httpx, "post", side_effect=[minute, _groq_response(MODEL_OUTPUT)]) as post:
            out = ai.summarize_job_with_ai("Engineer", DESCRIPTION)
        self.assertEqual(out["_model"], "groq:m1")
        ai.time.sleep.assert_any_call(3.0)
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list], ["m1", "m1"])

    def test_model_still_rate_limited_moves_to_next_model(self):
        minute = _rate_limited("Rate limit reached on tokens per minute (TPM)")
        with patch.object(ai.httpx, "post", side_effect=[minute] * 4 + [_groq_response(MODEL_OUTPUT)]) as post:
            out = ai.summarize_job_with_ai("Engineer", DESCRIPTION)
        self.assertEqual(out["_model"], "groq:m2")
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list], ["m1"] * 4 + ["m2"])

    def test_every_model_rate_limited_is_temporary(self):
        minute = _rate_limited("Rate limit reached on tokens per minute (TPM)")
        with patch.object(ai.httpx, "post", side_effect=[minute] * 8):
            with self.assertRaises(ai.AITemporaryError):
                ai.summarize_job_with_ai("Engineer", DESCRIPTION)

    @override_settings(GEMINI_API_KEY="gem-key", GEMINI_MODEL="gemini-test")
    def test_rate_limited_groq_falls_back_to_gemini(self):
        minute = _rate_limited("Rate limit reached on tokens per minute (TPM)")
        with patch.object(ai.httpx, "post", side_effect=[minute] * 8 + [_gemini_response(MODEL_OUTPUT)]):
            out = ai.summarize_job_with_ai("Engineer", DESCRIPTION)
        self.assertEqual(out["_model"], "gemini:gemini-test")

    def test_uses_token_limit_reported_by_groq(self):
        resp = _groq_response(MODEL_OUTPUT)
        resp.headers = {"x-ratelimit-limit-tokens": "6000"}
        with patch.object(ai.httpx, "post", return_value=resp):
            ai.summarize_job_with_ai("Engineer", DESCRIPTION)
        self.assertEqual(ai._groq_pool().tpm["m1"], 6000)

    def test_all_models_out_raises_quota_exhausted(self):
        daily = _rate_limited("on requests per day (RPD)")
        with patch.object(ai.httpx, "post", side_effect=[daily, daily]):
            with self.assertRaises(ai.AIQuotaExhausted):
                ai.summarize_job_with_ai("Engineer", DESCRIPTION)

    @override_settings(GEMINI_API_KEY="gem-key", GEMINI_MODEL="gemini-test")
    def test_falls_back_to_gemini_when_groq_is_out(self):
        daily = _rate_limited("on tokens per day (TPD)")
        with patch.object(ai.httpx, "post", side_effect=[daily, daily, _gemini_response(MODEL_OUTPUT)]):
            out = ai.summarize_job_with_ai("Engineer", DESCRIPTION)
        self.assertEqual(out["_model"], "gemini:gemini-test")

    def test_reasoning_block_is_stripped(self):
        resp = _groq_response(MODEL_OUTPUT)
        resp.json.return_value["choices"][0]["message"]["content"] = (
            "<think>plan</think>\n```json\n" + json.dumps(MODEL_OUTPUT) + "\n```"
        )
        with patch.object(ai.httpx, "post", return_value=resp):
            out = ai.summarize_job_with_ai("Engineer", DESCRIPTION)
        self.assertEqual(out["summary"], MODEL_OUTPUT["summary"])


class ModelPoolTests(SimpleTestCase):
    def test_spreads_requests_by_minute_token_budget(self):
        pool = ai._GroqModelPool(["a", "b"], tpm=8000)
        self.assertEqual([pool.acquire(3000) for _ in range(4)], ["a", "a", "b", "b"])

    def test_returns_none_when_all_exhausted(self):
        pool = ai._GroqModelPool(["a"], tpm=8000)
        pool.mark_exhausted("a")
        self.assertIsNone(pool.acquire(100))


class TrimPostingTests(SimpleTestCase):
    def test_drops_company_and_benefit_sections_and_caps_tokens(self):
        text = ("About Acme\nWe are the leading platform.\n\nResponsibilities\n- Build APIs\n\n"
                "Benefits\n- Free lunch\n\nRequirements\n- Python")
        trimmed = ai.trim_posting(text, 1000)
        self.assertNotIn("leading platform", trimmed)
        self.assertNotIn("Free lunch", trimmed)
        self.assertIn("Build APIs", trimmed)
        self.assertIn("Python", trimmed)
        self.assertLessEqual(ai.estimate_tokens(ai.trim_posting("word " * 5000, 300)), 300)

    def test_georgian_is_counted_as_more_tokens(self):
        self.assertGreater(ai.estimate_tokens("პითონი" * 100), ai.estimate_tokens("python" * 100))


class StoredSummaryTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Acme", platform="greenhouse")
        self.job = Job.objects.create(
            title="Senior Backend Engineer", company=company, platform="greenhouse",
            external_job_id="1", description=DESCRIPTION,
        )
        self.result = ai.validate_ai_result(MODEL_OUTPUT, DESCRIPTION, self.job.title)

    def test_rule_based_parsers_do_not_overwrite_current_summary(self):
        ai.apply_ai_result(self.job, self.result)
        self.job.save()
        self.job.skills_required = ["Illustrator", "Notion"]
        self.job.responsibilities = "• Acme builds the AI orchestration platform."
        self.job.save(update_fields=["skills_required", "responsibilities"])
        self.job.refresh_from_db()
        self.assertEqual(self.job.skills_required, ["sql", "python"])
        self.assertEqual(self.job.skills_preferred, ["Kubernetes"])
        self.assertIn("Jira", self.job.tech_stack)
        self.assertTrue(self.job.responsibilities.startswith("• Build and maintain"))
        self.assertEqual(self.job.structured_description["summary"], MODEL_OUTPUT["summary"])

    def test_changed_description_invalidates_summary(self):
        ai.apply_ai_result(self.job, self.result)
        self.job.save()
        self.job.description = DESCRIPTION + "\nNew: Go experience required."
        self.assertIsNone(ai.current_ai_result(self.job))


@override_settings(GROQ_API_KEY="", GEMINI_API_KEY="test-key")
class EnrichCommandTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", platform="greenhouse")
        self.job = Job.objects.create(
            title="Senior Backend Engineer", company=self.company, platform="greenhouse",
            external_job_id="1", description=DESCRIPTION,
        )
        Job.objects.create(
            title="Employer Role", company=self.company, platform="employer",
            external_job_id="e1", description=DESCRIPTION,
        )

    def _run(self, *args):
        out = StringIO()
        call_command("enrich_jobs_ai", *args, stdout=out)
        return out.getvalue()

    def test_summarizes_fetched_jobs_once(self):
        result = ai.validate_ai_result(MODEL_OUTPUT, DESCRIPTION, self.job.title)
        target = "jobs.management.commands.enrich_jobs_ai.summarize_job_with_ai"
        with patch(target, return_value=result) as summarize:
            self._run()
            self._run()
        self.assertEqual(summarize.call_count, 1)  # employer job skipped; second run finds nothing new
        self.job.refresh_from_db()
        self.assertEqual(self.job.skills_required, ["sql", "python"])
        self.assertIsNotNone(ai.current_ai_result(self.job))

    def test_stops_after_repeated_failures(self):
        for i in range(2, 30):
            Job.objects.create(title=f"Engineer {i}", company=self.company, platform="greenhouse",
                               external_job_id=str(i), description=DESCRIPTION)
        target = "jobs.management.commands.enrich_jobs_ai.summarize_job_with_ai"
        with patch(target, return_value=None):
            out = self._run("--workers", "1")
        self.assertIn("10 calls failed in a row", out)

    def test_stops_when_free_quota_is_used_up(self):
        Job.objects.create(title="Engineer 2", company=self.company, platform="greenhouse",
                           external_job_id="2", description=DESCRIPTION)
        result = ai.validate_ai_result(MODEL_OUTPUT, DESCRIPTION, self.job.title)
        result["_model"] = "groq:m1"
        target = "jobs.management.commands.enrich_jobs_ai.summarize_job_with_ai"
        with patch(target, side_effect=[result, ai.AIQuotaExhausted()]):
            out = self._run("--workers", "1")
        self.assertIn("quota used up", out)
        self.assertIn("Summarized 1 job(s)", out)
        self.assertIn("groq:m1: 1", out)

    @override_settings(GEMINI_API_KEY="")
    def test_without_key_does_nothing(self):
        self.assertIn("is set; skipping", self._run())

    def test_rate_limited_job_is_postponed_without_counting_an_attempt(self):
        target = "jobs.management.commands.enrich_jobs_ai.summarize_job_with_ai"
        with patch(target, side_effect=ai.AITemporaryError("busy")):
            out = self._run("--workers", "1")
        self.assertIn("1 postponed", out)
        self.job.refresh_from_db()
        self.assertNotIn("ai_failed", self.job.structured_description or {})

    def test_gives_up_on_a_posting_after_repeated_failures(self):
        target = "jobs.management.commands.enrich_jobs_ai.summarize_job_with_ai"
        with patch(target, return_value=None) as summarize:
            for _ in range(ai.AI_MAX_ATTEMPTS + 1):
                self._run("--workers", "1")
        self.assertEqual(summarize.call_count, ai.AI_MAX_ATTEMPTS)
        self.job.refresh_from_db()
        self.assertTrue(ai.ai_gave_up(self.job))
        self.assertFalse(Job.objects.filter(ai.ai_pending_q(), pk=self.job.pk).exists())


class AIOnlyListingTests(TestCase):
    """Fetched jobs are listed only once a summary for their current text is stored."""

    def setUp(self):
        self.company = Company.objects.create(name="Acme", platform="greenhouse")
        self.job = Job.objects.create(
            title="Senior Backend Engineer", company=self.company, platform="greenhouse",
            external_job_id="1", description=DESCRIPTION,
        )
        self.employer_job = Job.objects.create(
            title="Employer Role", company=self.company, platform="employer",
            external_job_id="e1", description=DESCRIPTION,
        )

    def _listed_ids(self):
        from .models import visible_jobs_q

        return set(Job.objects.filter(visible_jobs_q()).values_list("pk", flat=True))

    def test_fetched_job_waits_for_summary_employer_job_does_not(self):
        self.assertEqual(self._listed_ids(), {self.employer_job.pk})
        self.assertTrue(Job.objects.filter(ai.ai_pending_q(), pk=self.job.pk).exists())
        ai.apply_ai_result(self.job, ai.validate_ai_result(MODEL_OUTPUT, DESCRIPTION, self.job.title))
        self.job.save()
        self.assertEqual(self._listed_ids(), {self.job.pk, self.employer_job.pk})
        self.assertFalse(Job.objects.filter(ai.ai_pending_q(), pk=self.job.pk).exists())

    def test_changed_posting_is_hidden_until_summarized_again(self):
        ai.apply_ai_result(self.job, ai.validate_ai_result(MODEL_OUTPUT, DESCRIPTION, self.job.title))
        self.job.save()
        self.job.description = DESCRIPTION + "\nNew: Go experience required."
        self.job.save()
        self.assertNotIn(self.job.pk, self._listed_ids())
        self.assertTrue(Job.objects.filter(ai.ai_pending_q(), pk=self.job.pk).exists())

    def test_v1_api_lists_only_summarized_jobs(self):
        from django.urls import reverse

        res = self.client.get(reverse("job-list"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual([j["id"] for j in res.data["results"]], [self.employer_job.pk])

    def test_trim_backlog_keeps_newest_and_jobs_with_applications(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import JobApplication

        now = timezone.now()
        Job.objects.filter(pk=self.job.pk).update(posted_at=now - timedelta(days=9))
        jobs = [
            Job.objects.create(title=f"Engineer {i}", company=self.company, platform="greenhouse",
                               external_job_id=f"n{i}", description=DESCRIPTION, posted_at=now - timedelta(days=i))
            for i in range(3)
        ]
        JobApplication.objects.create(external_user_id="u1", job=self.job, applied_at=now)
        call_command("trim_ai_backlog", "--keep", "2", stdout=StringIO())
        self.assertEqual(Job.objects.count(), 5)  # dry run
        call_command("trim_ai_backlog", "--keep", "2", "--delete", stdout=StringIO())
        remaining = set(Job.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {jobs[0].pk, jobs[1].pk, self.job.pk, self.employer_job.pk})

    @override_settings(AI_ONLY_LISTINGS=False)
    def test_switch_lists_every_job(self):
        self.assertEqual(self._listed_ids(), {self.job.pk, self.employer_job.pk})
