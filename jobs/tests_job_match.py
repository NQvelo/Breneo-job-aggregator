"""Per-user job match score and internal match endpoints."""

from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from jobs.match_score import parse_snapshot, score_job
from jobs.models import Company, Job
from jobs.skill_variants import normalize_skill_name, normalize_skill_list

INTERNAL_KEY = "test-internal-key"


def _headers():
    return {"HTTP_X_INTERNAL_KEY": INTERNAL_KEY}


def _snapshot(**overrides):
    payload = {
        "userId": "user-1",
        "profileVersion": "v1",
        "skills": ["JavaScript", "React"],
        "seniority": "senior",
        "yearsExperienceTotal": 2,
        "industryYears": {"fintech": 3},
        "languages": ["English B1"],
    }
    payload.update(overrides)
    return payload


@override_settings(INTERNAL_API_KEY=INTERNAL_KEY)
class SkillAndScoreTests(TestCase):
    def test_variant_map_matches_the_app(self):
        self.assertEqual(normalize_skill_name("  JavaScript "), "javascript")
        self.assertEqual(normalize_skill_name("Search Engine Optimization"), "seo")
        self.assertEqual(normalize_skill_name("QuickBooks"), "quickbooks")
        self.assertEqual(normalize_skill_name("Epic EMR"), "epic ehr")
        self.assertEqual(normalize_skill_name("financial modelling"), "financial modeling")
        self.assertEqual(normalize_skill_name("Node.js"), "node.js")
        self.assertEqual(normalize_skill_name("JS"), "javascript")
        self.assertEqual(normalize_skill_name("nodejs"), "javascript")
        self.assertEqual(normalize_skill_name("node"), "node.js")
        self.assertEqual(normalize_skill_name("PostgreSQL"), "sql")
        self.assertEqual(normalize_skill_name("React.js"), "react")
        self.assertEqual(normalize_skill_list(["JavaScript", "Node.js", "JS"]), ["javascript", "node.js"])

    def test_same_snapshot_and_job_always_return_the_same_integer(self):
        job = _card()
        snapshot = parse_snapshot(_snapshot())
        first = score_job(job, snapshot)
        second = score_job(job, snapshot)
        self.assertEqual(first, second)
        self.assertEqual(first.skills_percent, 50)
        self.assertEqual(first.experience_percent, 71)
        self.assertEqual(first.industry_percent, 100)
        self.assertEqual(first.match_percent, 50)

    def test_null_rings_count_as_zero_and_stay_null(self):
        job = _card(skills_required=[], seniority=None, min_years_experience=None, industry_tags="", languages_required=[])
        score = score_job(job, parse_snapshot(_snapshot(skills=["Python"], seniority="unknown", yearsExperienceTotal=None, industryYears={}, languages=[])))
        self.assertIsNone(score.skills_percent)
        self.assertIsNone(score.experience_percent)
        self.assertIsNone(score.industry_percent)
        self.assertEqual(score.match_percent, 0)

    def test_skill_coverage_ignores_preferred_skills(self):
        job = _card(skills_required=["python"])
        job.skills_preferred = ["react"]
        job.tech_stack = ["react"]
        score = score_job(job, parse_snapshot(_snapshot(skills=["Python"], seniority="mid", yearsExperienceTotal=None, industryYears={}, languages=[])))
        self.assertEqual(score.skills_percent, 100)

    def test_experience_bands(self):
        snapshot = parse_snapshot(_snapshot(skills=[], seniority="senior", yearsExperienceTotal=None, industryYears={}, languages=[]))
        self.assertEqual(score_job(_card(seniority="senior", min_years_experience=None, industry_tags="", skills_required=["python"]), snapshot).experience_percent, 100)
        self.assertEqual(score_job(_card(seniority="mid", min_years_experience=None, industry_tags="", skills_required=["python"]), snapshot).experience_percent, 85)
        self.assertEqual(score_job(_card(seniority="junior", min_years_experience=None, industry_tags="", skills_required=["python"]), snapshot).experience_percent, 75)
        self.assertEqual(score_job(_card(seniority="lead", min_years_experience=None, industry_tags="", skills_required=["python"]), snapshot).experience_percent, 55)
        self.assertEqual(score_job(_card(seniority="lead", min_years_experience=None, industry_tags="", skills_required=["python"]), parse_snapshot(_snapshot(skills=[], seniority="intern", yearsExperienceTotal=None, industryYears={}, languages=[]))).experience_percent, 25)
        unknown = parse_snapshot(_snapshot(skills=[], seniority="unknown", yearsExperienceTotal=None, industryYears={}, languages=[]))
        self.assertEqual(score_job(_card(seniority="mid", min_years_experience=None, industry_tags="", skills_required=["python"]), unknown).experience_percent, 50)
        self.assertIsNone(score_job(_card(seniority=None, min_years_experience=None, industry_tags="", skills_required=["python"]), snapshot).experience_percent)

    def test_years_and_seniority_blend(self):
        snapshot = parse_snapshot(_snapshot(skills=[], seniority="mid", yearsExperienceTotal=2, industryYears={}, languages=[]))
        score = score_job(_card(seniority="mid", min_years_experience=4, industry_tags="", skills_required=["python"]), snapshot)
        self.assertEqual(score.experience_percent, 80)

    def test_years_only_when_seniority_missing(self):
        snapshot = parse_snapshot(_snapshot(skills=[], seniority="mid", yearsExperienceTotal=2, industryYears={}, languages=[]))
        enough = score_job(_card(seniority=None, min_years_experience=2, industry_tags="", skills_required=["python"]), snapshot)
        short = score_job(_card(seniority=None, min_years_experience=4, industry_tags="", skills_required=["python"]), snapshot)
        self.assertEqual(enough.experience_percent, 100)
        self.assertEqual(short.experience_percent, 50)

    def test_industry_exact_related_and_empty(self):
        user = parse_snapshot(_snapshot(skills=[], seniority="unknown", yearsExperienceTotal=None, industryYears={"fintech": 5}, languages=[]))
        exact = score_job(_card(industry_tags="fintech", skills_required=[], seniority=None), user)
        related = score_job(_card(industry_tags="banking", skills_required=[], seniority=None), user)
        none = score_job(_card(industry_tags="", skills_required=[], seniority=None), user)
        no_years = score_job(
            _card(industry_tags="fintech", skills_required=[], seniority=None),
            parse_snapshot(_snapshot(skills=[], seniority="unknown", yearsExperienceTotal=None, industryYears={}, languages=[])),
        )
        self.assertEqual(exact.industry_percent, 100)
        self.assertEqual(related.industry_percent, 70)
        self.assertIsNone(none.industry_percent)
        self.assertEqual(no_years.industry_percent, 0)

    def test_finance_synonym_on_the_job_only(self):
        user = parse_snapshot(_snapshot(skills=[], seniority="unknown", yearsExperienceTotal=None, industryYears={"fintech": 1}, languages=[]))
        score = score_job(_card(industry_tags="finance", skills_required=[], seniority=None), user)
        self.assertEqual(score.industry_percent, 100)

    def test_language_penalty_is_only_on_the_overall(self):
        base = _snapshot(languages=["English C1"], seniority="mid", yearsExperienceTotal=None, industryYears={}, skills=["JavaScript", "Python"])
        penalized = _snapshot(languages=["English B1"], seniority="mid", yearsExperienceTotal=None, industryYears={}, skills=["JavaScript", "Python"])
        job = _card(languages_required=["English C1"], seniority="mid", min_years_experience=None, industry_tags="")
        full = score_job(job, parse_snapshot(base))
        docked = score_job(job, parse_snapshot(penalized))
        self.assertEqual(full.skills_percent, docked.skills_percent)
        self.assertEqual(full.match_percent, 80)
        self.assertEqual(docked.match_percent, 60)


def _card(**overrides):
    class Card:
        pass

    card = Card()
    card.skills_required = ["JavaScript", "Python"]
    card.seniority = "mid"
    card.min_years_experience = 4
    card.industry_tags = "fintech"
    card.languages_required = ["English C1"]
    for key, value in overrides.items():
        setattr(card, key, value)
    return card


@override_settings(INTERNAL_API_KEY=INTERNAL_KEY)
class MatchCardSaveTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Card Co")

    def _job(self, **kwargs):
        defaults = {
            "title": "Engineer",
            "company": self.company,
            "platform": "employer",
            "external_job_id": kwargs.pop("external_job_id"),
            "is_active": True,
        }
        defaults.update(kwargs)
        return Job.objects.create(**defaults)

    def test_stored_skills_are_normalized_and_not_extended_from_the_description(self):
        job = self._job(
            external_job_id="skills-1",
            skills_required=["JavaScript", "Node.js", "JS"],
            description="Must know Python, Django, and Kubernetes.",
            seniority="lead",
        )
        job.refresh_from_db()
        self.assertEqual(job.skills_required, ["javascript", "node.js"])
        self.assertEqual(job.seniority, "lead")

    def test_empty_skills_are_inferred_once(self):
        job = self._job(
            external_job_id="skills-2",
            title="Backend Engineer",
            platform="greenhouse",
            skills_required=[],
            description="Requirements: Python and Django.",
        )
        job.refresh_from_db()
        self.assertIn("python", job.skills_required)
        self.assertIn("django", job.skills_required)
        job.description = job.description + " Also Kubernetes and React."
        job.save()
        job.refresh_from_db()
        self.assertNotIn("kubernetes", job.skills_required)
        self.assertNotIn("react", job.skills_required)

    def test_seniority_comes_from_the_field_then_the_title(self):
        from_title = self._job(external_job_id="sen-1", title="Senior Backend Engineer", description="We need a junior mindset.")
        from_field = self._job(external_job_id="sen-2", title="Engineer", seniority="lead", description="Senior role, 8 years.")
        missing = self._job(external_job_id="sen-3", title="Engineer", description="Senior role with 8 years of experience.")
        self.assertEqual(from_title.seniority, "senior")
        self.assertEqual(from_field.seniority, "lead")
        self.assertIsNone(missing.seniority)


@override_settings(INTERNAL_API_KEY=INTERNAL_KEY)
class InternalMatchApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.company = Company.objects.create(name="Match Co")
        self.now = timezone.now()

    def _job(self, external_job_id, **kwargs):
        posted = kwargs.pop("posted_at", self.now)
        defaults = {
            "title": "Engineer",
            "company": self.company,
            "platform": "employer",
            "external_job_id": external_job_id,
            "location": "Berlin",
            "location_country": "Germany",
            "skills_required": ["Python"],
            "seniority": "mid",
            "is_active": True,
            "posted_at": posted,
        }
        defaults.update(kwargs)
        return Job.objects.create(**defaults)

    def _post(self, path, body):
        return self.client.post(path, body, format="json", **_headers())

    def test_search_returns_filtered_matches_highest_first(self):
        older = self._job(
            "react-older",
            title="React Engineer",
            skills_required=["Python", "JavaScript"],
            seniority="mid",
            posted_at=self.now - timedelta(days=10),
        )
        newer = self._job(
            "react-newer",
            title="React Developer",
            skills_required=["Python"],
            seniority="junior",
            posted_at=self.now,
        )
        self._job("accountant", title="Accountant", skills_required=["Python"], seniority="mid")
        self._job("react-other-skill", title="React Designer", skills_required=["Go"], seniority="mid")

        body = {
            "userId": "user-1",
            "profileVersion": "search-1",
            "skills": ["Python"],
            "seniority": "mid",
            "yearsExperienceTotal": None,
            "industryYears": {},
            "languages": [],
            "title": ["React"],
            "limit": 10,
        }
        response = self._post("/internal/job-matches/search", body)
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data]
        self.assertCountEqual(ids, [older.id, newer.id])
        self.assertGreater(response.data[0]["match_percent"], 0)
        self.assertGreaterEqual(response.data[0]["match_percent"], response.data[1]["match_percent"])

    def test_rejects_missing_key(self):
        response = self.client.post("/internal/job-matches", _snapshot() | {"scope": "worldwide", "limit": 10}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_list_and_one_return_the_same_integer(self):
        self.company.logo = "https://cdn.example/logo.png"
        self.company.save(update_fields=["logo"])
        job = self._job(
            "golden",
            skills_required=["JavaScript", "Python"],
            seniority="mid",
            min_years_experience=4,
            industry_tags="fintech",
            languages_required=["English C1"],
            title="Engineer",
            salary="3000-5000",
            work_mode="remote",
            workplace_type="Remote",
            raw={"employment_type": "Full-time"},
        )
        body = _snapshot() | {"scope": "worldwide", "limit": 10}
        listed = self._post("/internal/job-matches", body)
        single = self._post("/internal/job-matches/one", _snapshot() | {"jobId": job.id})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(single.status_code, 200)
        self.assertIn("no-store", listed["Cache-Control"])
        row = listed.data[0]
        self.assertEqual(row["id"], job.id)
        self.assertEqual(row["company"], "Match Co")
        self.assertEqual(row["company_logo"], "https://cdn.example/logo.png")
        self.assertEqual(row["salary"], "3000-5000")
        self.assertEqual(row["employment_type"], "Full-time")
        self.assertEqual(row["work_mode"], "remote")
        self.assertEqual(row["workplace_type"], "Remote")
        self.assertEqual(row["match_percent"], 50)
        self.assertEqual(row["skills_percent"], 50)
        self.assertEqual(row["experience_percent"], 71)
        self.assertEqual(row["industry_percent"], 100)
        self.assertEqual(single.data["match_percent"], row["match_percent"])
        self.assertEqual(single.data["skills_percent"], row["skills_percent"])
        self.assertEqual(single.data["experience_percent"], row["experience_percent"])
        self.assertEqual(single.data["industry_percent"], row["industry_percent"])

    def test_candidate_filters_sort_and_sql_limit(self):
        older = self._job("older", seniority="mid", posted_at=self.now - timedelta(days=3))
        newer_weaker = self._job("weaker", seniority="junior", posted_at=self.now)
        self._job("lead", seniority="lead", posted_at=self.now)
        self._job("other-skill", skills_required=["Go"], seniority="mid")
        self._job("inactive", is_active=False)
        self._job("georgia", location="Tbilisi", location_country="Georgia", location_region=None)
        open_level = self._job("open-level", seniority=None, posted_at=self.now - timedelta(days=1))

        body = {
            "userId": "user-1",
            "profileVersion": "v1",
            "skills": ["Python"],
            "seniority": "mid",
            "yearsExperienceTotal": None,
            "industryYears": {},
            "languages": [],
            "scope": "worldwide",
            "limit": 10,
        }
        with CaptureQueriesContext(connection) as ctx:
            response = self._post("/internal/job-matches", body)
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data]
        self.assertEqual(ids, [older.id, newer_weaker.id, open_level.id])
        self.assertGreater(response.data[0]["match_percent"], response.data[-1]["match_percent"])
        job_sql = [query["sql"] for query in ctx.captured_queries if "jobs_job" in query["sql"]]
        self.assertTrue(any("LIMIT" in sql.upper() for sql in job_sql))
        self.assertTrue(all('"description"' not in sql for sql in job_sql))

    def test_unknown_seniority_skips_the_level_filter_but_keeps_the_skill(self):
        lead = self._job("lead-ok", seniority="lead")
        self._job("no-skill", skills_required=["Go"], seniority="lead")
        body = {
            "userId": "user-1",
            "profileVersion": "v2",
            "skills": ["Python"],
            "seniority": "unknown",
            "yearsExperienceTotal": None,
            "industryYears": {},
            "languages": [],
            "scope": "worldwide",
            "limit": 10,
        }
        response = self._post("/internal/job-matches", body)
        self.assertEqual([row["id"] for row in response.data], [lead.id])

    def test_no_skills_does_not_require_overlap(self):
        mid = self._job("mid-empty", skills_required=[])
        self._job("lead-empty", skills_required=[], seniority="lead")
        body = {
            "userId": "user-1",
            "profileVersion": "v3",
            "skills": [],
            "seniority": "mid",
            "yearsExperienceTotal": None,
            "industryYears": {},
            "languages": [],
            "scope": "worldwide",
            "limit": 10,
        }
        response = self._post("/internal/job-matches", body)
        self.assertEqual([row["id"] for row in response.data], [mid.id])
        self.assertIsNone(response.data[0]["skills_percent"])

    def test_scopes_split_georgia_and_worldwide(self):
        world = self._job("world")
        georgia = self._job("geo", location="Tbilisi", location_country="Georgia", location_region=None)
        base = {
            "userId": "user-1",
            "profileVersion": "v4",
            "skills": ["Python"],
            "seniority": "mid",
            "yearsExperienceTotal": None,
            "industryYears": {},
            "languages": [],
            "limit": 10,
        }
        georgia_ids = [row["id"] for row in self._post("/internal/job-matches", base | {"scope": "georgia"}).data]
        world_ids = [row["id"] for row in self._post("/internal/job-matches", base | {"scope": "worldwide"}).data]
        self.assertEqual(georgia_ids, [georgia.id])
        self.assertEqual(world_ids, [world.id])

    def test_same_day_keeps_stored_scores_until_profile_or_day_changes(self):
        job = self._job("cached", seniority="mid")
        body = {
            "userId": "user-1",
            "profileVersion": "v5",
            "skills": ["Python"],
            "seniority": "mid",
            "yearsExperienceTotal": None,
            "industryYears": {},
            "languages": [],
            "scope": "worldwide",
            "limit": 10,
        }
        first = self._post("/internal/job-matches", body)
        self.assertEqual(first.data[0]["match_percent"], 80)
        Job.objects.filter(pk=job.id).update(seniority="senior")
        second = self._post("/internal/job-matches", body)
        self.assertEqual(second.data[0]["match_percent"], 80)
        single = self._post("/internal/job-matches/one", body | {"jobId": job.id})
        self.assertEqual(single.data["match_percent"], 67)
        bumped = self._post("/internal/job-matches", body | {"profileVersion": "v6"})
        self.assertEqual(bumped.data[0]["match_percent"], 67)

    def test_daily_refresh_adds_new_jobs_and_keeps_old_matches(self):
        from jobs.models import UserJobMatch
        from jobs.user_match_store import refresh_all_stored_profiles

        older = self._job("keep-me", seniority="mid", posted_at=self.now - timedelta(days=2))
        body = {
            "userId": "user-1",
            "profileVersion": "daily",
            "skills": ["Python"],
            "seniority": "mid",
            "yearsExperienceTotal": None,
            "industryYears": {},
            "languages": [],
            "scope": "worldwide",
            "limit": 1,
        }
        first = self._post("/internal/job-matches", body)
        self.assertEqual([row["id"] for row in first.data], [older.id])

        newer = self._job("new-today", seniority="mid", posted_at=self.now)
        same_day = self._post("/internal/job-matches", body)
        self.assertEqual([row["id"] for row in same_day.data], [older.id])

        refresh_all_stored_profiles()
        after_cron = self._post("/internal/job-matches", body)
        self.assertEqual([row["id"] for row in after_cron.data], [newer.id, older.id])
        self.assertEqual(UserJobMatch.objects.filter(user_id="user-1", scope="worldwide").count(), 2)

    def test_newer_post_wins_equal_scores(self):
        older = self._job("tie-old", posted_at=self.now - timedelta(days=2))
        newer = self._job("tie-new", posted_at=self.now)
        body = {
            "userId": "user-1",
            "profileVersion": "ties",
            "skills": ["Python"],
            "seniority": "mid",
            "yearsExperienceTotal": None,
            "industryYears": {},
            "languages": [],
            "scope": "worldwide",
            "limit": 10,
        }
        response = self._post("/internal/job-matches", body)
        self.assertEqual([row["id"] for row in response.data], [newer.id, older.id])

    def test_user_match_tables_exist(self):
        tables = set(connection.introspection.table_names())
        self.assertIn("jobs_usermatchsnapshot", tables)
        self.assertIn("jobs_userjobmatch", tables)
