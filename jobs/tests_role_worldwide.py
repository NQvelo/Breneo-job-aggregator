from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from . import fetchers
from . import role_categories as rc
from .management.commands import fetch_jobs as fetch_jobs_cmd
from .models import Company, Job
from .remote_worldwide_filter import is_international_listing_allowed


class RoleFamilyTests(SimpleTestCase):
    def test_each_family_has_a_matching_title(self):
        cases = {
            "Senior Backend Developer (Python)": rc.SOFTWARE_ENGINEERING,
            "Site Reliability Engineer": rc.DEVOPS_CLOUD,
            "Data Engineer": rc.DATA_AI,
            "Machine Learning Researcher": rc.DATA_AI,
            "Product Designer": rc.DESIGN,
            "Senior Product Manager": rc.PRODUCT_BUSINESS_ANALYSIS,
            "Business Analyst": rc.PRODUCT_BUSINESS_ANALYSIS,
            "Technical Program Manager": rc.PROJECT_PROGRAM_MANAGEMENT,
            "Scrum Master": rc.PROJECT_PROGRAM_MANAGEMENT,
            "Growth Marketing Manager": rc.MARKETING,
            "Account Executive, EMEA": rc.SALES_SUCCESS,
            "Customer Success Manager": rc.SALES_SUCCESS,
            "Senior Accountant": rc.FINANCE_ACCOUNTING,
            "Technical Recruiter": rc.HR_RECRUITING,
            "Customer Support Specialist": rc.CUSTOMER_SUPPORT,
            "Executive Assistant": rc.OPERATIONS_ADMIN,
            "Registered Nurse (Telehealth)": rc.HEALTHCARE,
            "Online English Teacher": rc.EDUCATION,
            "Mechanical Engineer": rc.ENGINEERING_TRADES,
            "HVAC Technician": rc.ENGINEERING_TRADES,
            "Technical Writer": rc.WRITING_MEDIA,
            "Video Editor": rc.WRITING_MEDIA,
            "GRC Analyst": rc.FINANCE_ACCOUNTING,
            "Global Alliance Lead, Capgemini": rc.SALES_SUCCESS,
            "Client Value Partner (CVP) - Utilities": rc.SALES_SUCCESS,
        }
        for title, family in cases.items():
            with self.subTest(title=title):
                self.assertEqual(rc.classify_role_family(title), family)
        self.assertEqual(len(rc.ROLE_FAMILIES), 16)

    def test_roles_outside_the_families_are_rejected(self):
        for title in ("Truck Driver", "Head Chef", "Security Guard", "Legal Counsel",
                      "Warehouse Associate", "Barista", "Housekeeper", ""):
            with self.subTest(title=title):
                self.assertIsNone(rc.classify_role_family(title))

    def test_vague_engineering_title_uses_description_stack(self):
        self.assertEqual(
            rc.classify_role_family("Member of Technical Staff", "We build with Python and Kubernetes."),
            rc.SOFTWARE_ENGINEERING,
        )
        self.assertIsNone(rc.classify_role_family("Member of Technical Staff", "Great culture."))


def _intl_item(ext_id, title, location, description="Work from anywhere in the world."):
    return {
        "title": title,
        "company": "Acme",
        "location": location,
        "description": description,
        "apply_url": f"https://acme.example/jobs/{ext_id}",
        "platform": "greenhouse",
        "external_job_id": ext_id,
        "raw": {},
    }


INTL_SOURCE = {"name": "Acme", "platform": "greenhouse", "handle": "acme"}


class WorldwideDefaultTests(TestCase):
    FEED = [
        _intl_item("1", "Growth Marketing Manager", "Remote - Worldwide"),
        _intl_item("2", "Senior Software Engineer", "Remote - US",
                   description="Must be located in the United States."),
        _intl_item("3", "Truck Driver", "Remote - Worldwide"),
        _intl_item("4", "Registered Nurse", "Anywhere in the world"),
        _intl_item("5", "Backend Engineer", "Berlin, Germany", description="Onsite in Berlin."),
        _intl_item("6", "Product Designer", "Remote", description="Join our design team."),
        _intl_item("7", "Data Analyst", "Tbilisi, Georgia", description="Onsite in our Tbilisi office."),
        _intl_item("8", "Software Engineer", "Atlanta, Georgia", description="Onsite in Atlanta."),
        _intl_item("9", "Frontend Developer", "Remote",
                   description="You must be located in the United States."),
        _intl_item("10", "QA Engineer", "Remote - Kenya", description="Remote role."),
        _intl_item("11", "DevOps Engineer", "Warsaw, Poland / Tbilisi, Georgia", description="Hybrid."),
    ]

    def _run(self, *args):
        fake = lambda *a, **k: list(self.FEED)  # noqa: E731
        with patch.object(fetch_jobs_cmd, "COMPANIES", [INTL_SOURCE]), patch.dict(
            fetch_jobs_cmd.PLATFORM_TO_FETCHER, {"greenhouse": fake}
        ):
            call_command("fetch_jobs", "--no-ai-limit", *args, stdout=StringIO())

    def _active_ids(self):
        return set(Job.objects.filter(platform="greenhouse", is_active=True)
                   .values_list("external_job_id", flat=True))

    def test_default_keeps_placeless_remote_and_georgia_jobs(self):
        self._run()
        self.assertEqual(self._active_ids(), {"1", "4", "6", "7", "11"})

    def test_allow_region_remote_also_keeps_region_locked_remote(self):
        self._run("--allow-region-remote")
        self.assertEqual(self._active_ids(), {"1", "2", "4", "6", "7", "9", "10", "11"})

    def test_stored_region_locked_job_is_hidden(self):
        company = Company.objects.create(name="Acme", platform="greenhouse")
        old = Job.objects.create(
            title="Senior Software Engineer", company=company, platform="greenhouse",
            external_job_id="2", location="Remote - US", is_active=True, last_seen_at=timezone.now(),
        )
        self._run()
        old.refresh_from_db()
        self.assertFalse(old.is_active)


USA_MULTI_SITE = (
    "USA - Austin, TX / USA - Remote, WY / USA - Remote, WI / USA - Remote, WV / USA - Remote, WA / "
    "USA - Remote, VA / USA - Remote, VT / USA - Remote, UT / USA - Remote, TX / USA - Remote, SC / USA - Remo"
)


class PruneStoredInternationalJobsTests(TestCase):
    def test_usa_remote_rows_are_hidden_without_fetching(self):
        company = Company.objects.create(name="Acme", platform="workday")
        kept = Job.objects.create(title="Backend Engineer", company=company, platform="workday",
                                  external_job_id="ok", location="Remote", workplace_type="Remote")
        usa = Job.objects.create(title="Backend Engineer", company=company, platform="workday",
                                 external_job_id="usa", location=USA_MULTI_SITE, workplace_type="Remote")
        local = Job.objects.create(title="ბუღალტერი", company=company, platform="jobs.ge",
                                   external_job_id="ge", location="Tbilisi")
        out = StringIO()
        call_command("prune_international_jobs", stdout=out)
        for job in (kept, usa, local):
            job.refresh_from_db()
        self.assertFalse(usa.is_active)
        self.assertTrue(kept.is_active)
        self.assertTrue(local.is_active)
        self.assertIn("Hid 1", out.getvalue())


class InternationalLocationRuleTests(SimpleTestCase):
    def _allowed(self, location, description="", **extra):
        return is_international_listing_allowed(
            {"title": "Engineer", "location": location, "description": description, **extra}
        )

    def test_remote_without_a_place_is_kept(self):
        for loc in ("Remote", "Remote (Global)", "Remote - Worldwide", "Anywhere", "Fully Remote"):
            with self.subTest(loc=loc):
                self.assertTrue(self._allowed(loc))
        self.assertTrue(self._allowed("", workplace_type="Remote"))

    def test_remote_tied_to_a_place_is_dropped(self):
        for loc in ("Remote - US", "Remote, EMEA", "Remote (Canada)", "Remote - Kenya", "Remote - CET time zone",
                    "Remote - Georgia, US", "Georgia - Atlanta Metro - Remote", "USA", USA_MULTI_SITE,
                    "USA - Remote", "USA Remote", "Remote USA", "US Remote", "Remote (US)",
                    "United States (Remote)", "Remote - Americas", "North America - Remote"):
            with self.subTest(loc=loc):
                self.assertFalse(self._allowed(loc))
        self.assertFalse(self._allowed("Remote", location_country="United States"))
        self.assertFalse(self._allowed("Remote", "Candidates must be authorized to work in the UK."))

    def test_georgia_locations_are_kept_in_any_work_mode(self):
        for loc in ("Tbilisi, Georgia", "Tbilisi", "Batumi, Georgia", "Remote - Tbilisi",
                    "Berlin, Germany / Tbilisi, Georgia"):
            with self.subTest(loc=loc):
                self.assertTrue(self._allowed(loc, workplace_type="Onsite"))
        self.assertTrue(self._allowed("", location_country="Georgia", workplace_type="Hybrid"))
        self.assertFalse(self._allowed("Atlanta, Georgia", workplace_type="Onsite"))
        # Workday "State - Site" rows: older code stored location_country="Georgia" on them.
        workday_raw = {"jobPostingInfo": {"country": {"descriptor": "United States of America"}}}
        self.assertFalse(self._allowed("Georgia - Remote", location_country="Georgia", raw=workday_raw))
        self.assertFalse(self._allowed("Georgia - Remote / Florida - Remote", location_country="Georgia",
                                       raw=workday_raw))
        self.assertFalse(self._allowed("Berlin, Germany", workplace_type="Onsite"))


def _jobs_ge_page(ids):
    rows = "".join(
        f'<tr><td><a href="https://jobs.ge/ka/?view=jobs&id={i}">Job {i}</a></td></tr>' for i in ids
    )
    return f'<div class="regularEntries"><table>{rows}</table></div>'.encode()


class JobsGeCategoryTests(SimpleTestCase):
    def _fake_get(self, pages, detail_calls):
        def get(url):
            resp = MagicMock()
            if "view=jobs" in url:
                detail_calls.append(url)
                resp.content = b"<html></html>"
            else:
                resp.content = _jobs_ge_page(pages.get(url, []))
            return resp
        return get

    def test_paginates_each_category_and_skips_known_details(self):
        url = fetchers.JOBS_GE_CATEGORY_URL.format
        pages = {
            url(page=1, cid=1): ["10", "11"],
            url(page=2, cid=1): ["10", "12"],  # VIP row 10 repeats on every page
            url(page=3, cid=1): ["10"],
            url(page=1, cid=2): ["11", "20"],  # 11 is cross-listed in two categories
        }
        detail_calls = []
        with patch.object(fetchers, "JOBS_GE_CATEGORY_IDS", (1, 2)), \
                patch.object(fetchers, "robots_allowed", return_value=True), \
                patch.object(fetchers, "_jobs_ge_get", side_effect=self._fake_get(pages, detail_calls)):
            jobs = fetchers.fetch_jobs_ge_listings(known_ids={"11", "12"}, max_detail_fetches=1)

        # 10 is opened (and dropped: the fake detail page has no duties). 11 and 12 are
        # stored; 20 is over the per-run cap.
        self.assertEqual([j["external_job_id"] for j in jobs], ["11", "12", "20"])
        self.assertEqual(len(detail_calls), 1)
        self.assertIn("id=10", detail_calls[0])
        by_id = {j["external_job_id"]: j for j in jobs}
        for ext_id in ("11", "12", "20"):
            self.assertTrue(by_id[ext_id].get("seen_only"))
            self.assertEqual(by_id[ext_id]["title"], f"Job {ext_id}")


class GeorgianBoardCategoryParamTests(SimpleTestCase):
    def test_hr_ge_searches_all_codes_and_skips_known_details(self):
        search = MagicMock()
        search.json.return_value = {"data": {"announcements": {"items": [
            {"announcementId": 1, "title": "Accountant", "customerName": "Bank"},
            {"announcementId": 2, "title": "Nurse", "customerName": "Clinic"},
        ], "totalCount": 2}}}
        detail = MagicMock()
        detail.json.return_value = {"data": {"announcement": {"description": "<p>Duties</p>"}}}
        with patch.object(fetchers.httpx, "post", return_value=search) as post, \
                patch.object(fetchers.httpx, "get", return_value=detail) as get:
            jobs = fetchers.fetch_hr_ge(known_ids={"1"})

        self.assertEqual(post.call_args.kwargs["json"]["SpecializationCodes"],
                         list(fetchers.HR_GE_SPECIALIZATION_CODES))
        self.assertEqual(get.call_count, 1)
        self.assertTrue(jobs[0]["seen_only"])
        self.assertEqual(jobs[0]["title"], "Accountant")
        self.assertEqual(jobs[1]["title"], "Nurse")

    def test_myjobs_ge_requests_all_categories_and_drops_others(self):
        resp = MagicMock()
        resp.json.return_value = {"data": [
            {"id": 1, "title": "Marketer", "category_data": {"id": 77}},
            {"id": 2, "title": "Bodyguard", "category_data": {"id": 655}},
            {"id": 1, "title": "Marketer", "category_data": {"id": 77}},
        ], "next_page_url": None}
        with patch.object(fetchers.httpx, "get", return_value=resp) as get:
            jobs = fetchers.fetch_myjobs_ge()
        categories = get.call_args.kwargs["params"]["categories"].split(",")
        self.assertEqual(sorted(int(c) for c in categories), sorted(fetchers.MYJOBS_GE_CATEGORY_IDS))
        self.assertEqual([j["title"] for j in jobs], ["Marketer"])

    def test_jobs_ss_ge_requests_all_spheres_without_title_filter(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.cookies.get.return_value = "token"
        search = MagicMock()
        search.json.return_value = {"result": {"items": [
            {"id": 5, "title": {"ka": "ბუღალტერი"}},
        ], "totalCount": 1}}
        client.post.return_value = search
        with patch.object(fetchers.httpx, "Client", return_value=client):
            jobs = fetchers.fetch_jobs_ss_ge()
        self.assertEqual(client.post.call_args.kwargs["json"]["sphereId"], list(fetchers.JOBS_SS_GE_SPHERE_IDS))
        self.assertEqual([j["title"] for j in jobs], ["ბუღალტერი"])
