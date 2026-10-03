from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from .fetchers import _jobs_ge_parse_published
from .management.commands import fetch_jobs as fetch_jobs_cmd
from .models import Company, Job, JobApplication

JOBS_GE_SOURCE = {
    "name": "Jobs.ge IT",
    "platform": "jobs.ge",
    "url": "https://jobs.ge/?cid=6",
    "dynamic_company": True,
}


def _feed_item(external_id: str, title: str = "Python Developer") -> dict:
    return {
        "title": title,
        "company": "Feed Co",
        "location": "Tbilisi",
        "location_country": "Georgia",
        "description": "მოვალეობები:\n- Build APIs\n- Write tests\n- Review code",
        "apply_url": "https://example.com/apply",
        "apply_email": None,
        "posted_at": timezone.now(),
        "platform": "jobs.ge",
        "external_job_id": external_id,
        "raw": {},
    }


class FetchJobsLifecycleTests(TestCase):
    def setUp(self):
        self.feed_company = Company.objects.create(name="Feed Co", platform="jobs.ge")
        self.employer_company = Company.objects.create(name="Employer Co", employer_created=True)

    def _run(self, feed):
        fake_fetcher = lambda *args, **kwargs: list(feed)  # noqa: E731
        with patch.object(fetch_jobs_cmd, "COMPANIES", [JOBS_GE_SOURCE]), patch.dict(
            fetch_jobs_cmd.PLATFORM_TO_FETCHER, {"jobs.ge": fake_fetcher}
        ):
            call_command("fetch_jobs", stdout=StringIO())

    def _fetched_job(self, external_id: str, last_seen_days_ago: int = 0, is_active: bool = True) -> Job:
        return Job.objects.create(
            title="Old Listing",
            company=self.feed_company,
            platform="jobs.ge",
            external_job_id=external_id,
            is_active=is_active,
            last_seen_at=timezone.now() - timedelta(days=last_seen_days_ago),
        )

    def test_new_job_is_saved_with_last_seen_at(self):
        self._run([_feed_item("100")])
        job = Job.objects.get(platform="jobs.ge", external_job_id="100")
        self.assertTrue(job.is_active)
        self.assertIsNotNone(job.last_seen_at)

    def test_paused_employer_job_and_applications_survive(self):
        employer_job = Job.objects.create(
            title="Paused Role",
            company=self.employer_company,
            platform="employer",
            external_job_id="employer-1",
            is_active=False,
        )
        JobApplication.objects.create(
            external_user_id="u1", job=employer_job, applied_at=timezone.now()
        )
        self._run([_feed_item("100")])
        self.assertTrue(Job.objects.filter(pk=employer_job.pk).exists())
        self.assertEqual(JobApplication.objects.filter(job=employer_job).count(), 1)

    def test_job_missing_from_feed_is_hidden_not_deleted(self):
        missing = self._fetched_job("200", last_seen_days_ago=1)
        self._run([_feed_item("100")])
        missing.refresh_from_db()
        self.assertFalse(missing.is_active)

    def test_job_missing_past_grace_period_is_deleted(self):
        stale = self._fetched_job("300", last_seen_days_ago=fetch_jobs_cmd.STALE_JOB_GRACE_DAYS + 1)
        self._run([_feed_item("100")])
        self.assertFalse(Job.objects.filter(pk=stale.pk).exists())

    def test_job_reappearing_in_feed_is_reactivated(self):
        hidden = self._fetched_job("400", last_seen_days_ago=2, is_active=False)
        self._run([_feed_item("400")])
        hidden.refresh_from_db()
        self.assertTrue(hidden.is_active)
        self.assertGreater(hidden.last_seen_at, timezone.now() - timedelta(minutes=5))

    def test_empty_source_leaves_existing_jobs_active(self):
        existing = self._fetched_job("500", last_seen_days_ago=1)
        with self.assertRaises(CommandError):
            self._run([])
        existing.refresh_from_db()
        self.assertTrue(existing.is_active)


class JobsGePublishedDateTests(TestCase):
    def test_parses_current_year(self):
        now = datetime(2026, 10, 3, 12, 0, tzinfo=dt_timezone.utc)
        parsed = _jobs_ge_parse_published("01 ოქტომბერი", now=now)
        self.assertEqual((parsed.year, parsed.month, parsed.day), (2026, 10, 1))

    def test_future_date_rolls_back_a_year(self):
        now = datetime(2027, 1, 5, 12, 0, tzinfo=dt_timezone.utc)
        parsed = _jobs_ge_parse_published("28 დეკემბერი", now=now)
        self.assertEqual((parsed.year, parsed.month, parsed.day), (2026, 12, 28))

    def test_unparseable_returns_none(self):
        self.assertIsNone(_jobs_ge_parse_published(""))
        self.assertIsNone(_jobs_ge_parse_published("yesterday"))
        self.assertIsNone(_jobs_ge_parse_published("03 unknown"))
