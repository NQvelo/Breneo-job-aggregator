from datetime import datetime, timezone

from django.test import TestCase

from jobs.fetchers import GE_TZ, _jobs_ge_parse_deadline, _parse_deadline
from jobs.models import Company, Job, visible_jobs_q


class JobDeadlineVisibilityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Deadline Co")
        # 2026-10-19 15:00 in Tbilisi
        self.now = datetime(2026, 10, 19, 15, 0, tzinfo=GE_TZ)

    def _job(self, ext_id, deadline, is_active=True):
        return Job.objects.create(
            title=f"Job {ext_id}",
            company=self.company,
            platform="hr.ge",
            external_job_id=ext_id,
            deadline=deadline,
            is_active=is_active,
        )

    def test_visible_until_one_day_after_deadline(self):
        self._job("none", None)
        self._job("tomorrow", datetime(2026, 10, 20, 0, 0, tzinfo=GE_TZ))
        self._job("today", datetime(2026, 10, 19, 0, 0, tzinfo=GE_TZ))
        self._job("yesterday", datetime(2026, 10, 18, 0, 0, tzinfo=GE_TZ))
        self._job("two_days_ago", datetime(2026, 10, 17, 23, 59, tzinfo=GE_TZ))
        self._job("inactive_future", datetime(2026, 11, 1, tzinfo=GE_TZ), is_active=False)

        visible = set(Job.objects.filter(visible_jobs_q(self.now)).values_list("external_job_id", flat=True))
        self.assertEqual(visible, {"none", "tomorrow", "today", "yesterday"})

    def test_georgia_date_used_not_utc(self):
        # 2026-10-19 22:00 UTC is already 2026-10-20 02:00 in Tbilisi, so an Oct 18 deadline has expired
        now_utc = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)
        self._job("deadline_18th", datetime(2026, 10, 18, 23, 59, tzinfo=GE_TZ))
        self.assertFalse(Job.objects.filter(visible_jobs_q(now_utc)).exists())
        self._job("deadline_19th", datetime(2026, 10, 19, 0, 0, tzinfo=GE_TZ))
        self.assertTrue(Job.objects.filter(visible_jobs_q(now_utc)).exists())


class DeadlineParsingTests(TestCase):
    def test_hr_ge_naive_is_georgia_time(self):
        dt = _parse_deadline("2026-11-14T23:59:00")
        self.assertEqual(dt, datetime(2026, 11, 14, 23, 59, tzinfo=GE_TZ))

    def test_jobs_ge_month_name(self):
        now = datetime(2026, 10, 19, 12, 0, tzinfo=GE_TZ)
        self.assertEqual(_jobs_ge_parse_deadline("14 ნოემბერი", now), datetime(2026, 11, 14, tzinfo=GE_TZ))
        self.assertEqual(_jobs_ge_parse_deadline("18 ოქტომბერი", now), datetime(2026, 10, 18, tzinfo=GE_TZ))

    def test_jobs_ge_rolls_into_next_year(self):
        now = datetime(2026, 12, 20, 12, 0, tzinfo=GE_TZ)
        self.assertEqual(_jobs_ge_parse_deadline("10 იანვარი", now), datetime(2027, 1, 10, tzinfo=GE_TZ))

    def test_jobs_ge_unparseable(self):
        self.assertIsNone(_jobs_ge_parse_deadline(""))
        self.assertIsNone(_jobs_ge_parse_deadline("soon"))
