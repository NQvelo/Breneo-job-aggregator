"""Georgia the country and Georgia the U.S. state must not share one location."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .job_normalizer import parse_stored_location_fields
from .location_resolver import (
    GEORGIA_AMBIGUOUS,
    GEORGIA_COUNTRY,
    GEORGIA_US_STATE,
    resolve_location,
)
from .management.commands import fetch_jobs as fetch_jobs_cmd
from .models import Company, Job


class ResolveGeorgiaTests(TestCase):
    def test_country_formats(self):
        tbilisi = resolve_location("Tbilisi, Georgia")
        self.assertEqual((tbilisi.city, tbilisi.country, tbilisi.georgia), ("Tbilisi", "Georgia", GEORGIA_COUNTRY))
        self.assertIsNone(tbilisi.region)

        batumi = resolve_location("Batumi, Georgia")
        self.assertEqual(batumi.city, "Batumi")
        self.assertEqual(batumi.georgia, GEORGIA_COUNTRY)

        labeled = resolve_location("Georgia, Country")
        self.assertEqual(labeled.country, "Georgia")
        self.assertEqual(labeled.georgia, GEORGIA_COUNTRY)
        self.assertIsNone(labeled.region)

        paren = resolve_location("Georgia (Country)")
        self.assertEqual(paren.georgia, GEORGIA_COUNTRY)

    def test_us_state_formats(self):
        atlanta = resolve_location("Atlanta, Georgia")
        self.assertEqual(atlanta.city, "Atlanta")
        self.assertEqual(atlanta.country, "USA")
        self.assertEqual(atlanta.region, "Georgia")
        self.assertEqual(atlanta.georgia, GEORGIA_US_STATE)

        savannah = resolve_location("Savannah, GA")
        self.assertEqual(savannah.city, "Savannah")
        self.assertEqual(savannah.country, "USA")
        self.assertEqual(savannah.region, "Georgia")

        labeled = resolve_location("Georgia (USA)")
        self.assertEqual(labeled.country, "USA")
        self.assertEqual(labeled.region, "Georgia")
        self.assertEqual(labeled.georgia, GEORGIA_US_STATE)

        united = resolve_location("Georgia, United States")
        self.assertEqual(united.georgia, GEORGIA_US_STATE)
        self.assertEqual(united.country, "USA")

    def test_bare_georgia_is_not_the_country_without_evidence(self):
        bare = resolve_location("Georgia")
        self.assertEqual(bare.georgia, GEORGIA_AMBIGUOUS)
        self.assertIsNone(bare.country)
        self.assertTrue(bare.country_authoritative)
        self.assertEqual(parse_stored_location_fields("Georgia"), (None, None))

    def test_bare_georgia_uses_description_and_source(self):
        country = resolve_location("Georgia", context="The team sits in Tbilisi and Batumi.")
        self.assertEqual(country.georgia, GEORGIA_COUNTRY)

        state = resolve_location("Georgia", context="HQ is in Atlanta, GA.")
        self.assertEqual(state.georgia, GEORGIA_US_STATE)
        self.assertEqual(state.country, "USA")

        both = resolve_location("Georgia", context="Offices in Tbilisi and Atlanta.")
        self.assertEqual(both.georgia, GEORGIA_AMBIGUOUS)

        board = resolve_location("Georgia", platform="jobs.ge")
        self.assertEqual(board.country, "Georgia")
        self.assertEqual(board.georgia, GEORGIA_COUNTRY)

    def test_other_locations_unchanged(self):
        self.assertEqual(parse_stored_location_fields("Berlin, Germany"), ("Berlin", "Germany"))
        self.assertEqual(parse_stored_location_fields("Paris, France"), ("Paris", "France"))
        self.assertEqual(parse_stored_location_fields("San Francisco, CA"), ("San Francisco", "USA"))
        self.assertEqual(parse_stored_location_fields("Chicago, IL; New York, NY"), ("Chicago", "USA"))
        self.assertEqual(parse_stored_location_fields("Toronto, ON"), ("Toronto", "Canada"))
        self.assertEqual(parse_stored_location_fields("London, England"), ("London", "United Kingdom"))
        self.assertEqual(parse_stored_location_fields("Austin, Texas"), ("Austin", "USA"))
        columbus = resolve_location("Columbus, OH")
        self.assertEqual(columbus.city, "Columbus")
        self.assertEqual(columbus.country, "USA")
        self.assertEqual(columbus.region, "Ohio")
        self.assertIsNone(columbus.georgia)
        city, country = parse_stored_location_fields("Boston, New England")
        self.assertEqual(city, "Boston, New England")
        self.assertIsNone(country)
        self.assertEqual(parse_stored_location_fields(None), (None, None))
        self.assertEqual(parse_stored_location_fields("   "), (None, None))

    def test_legacy_us_city_stored_as_country_is_repaired(self):
        repaired = resolve_location("Atlanta", stored_country="Georgia", platform="greenhouse")
        self.assertEqual(repaired.country, "USA")
        self.assertEqual(repaired.region, "Georgia")
        self.assertEqual(repaired.georgia, GEORGIA_US_STATE)

        kept = resolve_location("Tbilisi", stored_country="Georgia", platform="greenhouse")
        self.assertEqual(kept.country, "Georgia")
        self.assertEqual(kept.georgia, GEORGIA_COUNTRY)


def _job(company, **kwargs):
    defaults = {
        "title": "Engineer",
        "company": company,
        "work_mode": "remote",
        "seniority": "mid",
        "posted_at": timezone.now(),
        "is_active": True,
        "platform": "greenhouse",
    }
    defaults.update(kwargs)
    return Job.objects.create(**defaults)


class GeorgiaSearchFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name="Place Co", platform="greenhouse")
        self.tbilisi = _job(
            self.company,
            title="Tbilisi Role",
            location="Tbilisi, Georgia",
            platform="jobs.ge",
            external_job_id="tb",
        )
        self.batumi = _job(
            self.company,
            title="Batumi Role",
            location="Batumi, Georgia",
            platform="hr.ge",
            external_job_id="ba",
        )
        self.labeled_country = _job(
            self.company,
            title="Country Label",
            location="Georgia, Country",
            platform="employer",
            external_job_id="gc",
        )
        self.atlanta = _job(
            self.company,
            title="Atlanta Role",
            location="Atlanta, Georgia",
            platform="greenhouse",
            external_job_id="at",
        )
        self.savannah = _job(
            self.company,
            title="Savannah Role",
            location="Savannah, GA",
            platform="lever",
            external_job_id="sv",
        )
        self.bare = _job(
            self.company,
            title="Bare Georgia",
            location="Georgia",
            platform="greenhouse",
            external_job_id="bare",
        )
        self.berlin = _job(
            self.company,
            title="Berlin Role",
            location="Berlin, Germany",
            platform="greenhouse",
            external_job_id="ber",
        )
        self.paris = _job(
            self.company,
            title="Paris Role",
            location="Paris, France",
            platform="greenhouse",
            external_job_id="par",
        )
        # Rows already stored by the old parser: country "Georgia" and the state name removed.
        self.legacy_atlanta = _job(
            self.company,
            title="Legacy Atlanta",
            location="Legacy City",
            location_country="USA",
            platform="ashby",
            external_job_id="leg",
        )
        Job.objects.filter(pk=self.legacy_atlanta.pk).update(
            location="Atlanta",
            location_country="Georgia",
            location_region=None,
        )
        self.legacy_bare = _job(
            self.company,
            title="Legacy Bare",
            location="Keep",
            location_country="USA",
            platform="smartrecruiters",
            external_job_id="legbare",
        )
        Job.objects.filter(pk=self.legacy_bare.pk).update(
            location="Georgia",
            location_country="Georgia",
            location_region=None,
        )

    def _titles(self, url_name, params):
        response = self.client.get(reverse(url_name), params)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["title"] for row in response.data["results"]}

    def test_country_selection_excludes_us_state_and_other_countries(self):
        for params in (
            {"country": "Georgia"},
            {"country": "Georgia (Country)"},
            {"country": "ge"},
            {"location_country": "Georgia"},
            {"city": "Georgia (Country)"},
        ):
            titles = self._titles("job_search", params)
            self.assertIn("Tbilisi Role", titles, params)
            self.assertIn("Batumi Role", titles, params)
            self.assertIn("Country Label", titles, params)
            self.assertNotIn("Atlanta Role", titles, params)
            self.assertNotIn("Savannah Role", titles, params)
            self.assertNotIn("Bare Georgia", titles, params)
            self.assertNotIn("Legacy Atlanta", titles, params)
            self.assertNotIn("Legacy Bare", titles, params)
            self.assertNotIn("Berlin Role", titles, params)
            self.assertNotIn("Paris Role", titles, params)

    def test_us_state_selection_excludes_country_and_other_countries(self):
        for params in (
            {"country": "Georgia (USA)"},
            {"location_country": "Georgia (USA)"},
            {"city": "Georgia, USA"},
        ):
            titles = self._titles("job_search", params)
            self.assertIn("Atlanta Role", titles, params)
            self.assertIn("Savannah Role", titles, params)
            self.assertIn("Legacy Atlanta", titles, params)
            self.assertNotIn("Tbilisi Role", titles, params)
            self.assertNotIn("Batumi Role", titles, params)
            self.assertNotIn("Country Label", titles, params)
            self.assertNotIn("Bare Georgia", titles, params)
            self.assertNotIn("Legacy Bare", titles, params)
            self.assertNotIn("Berlin Role", titles, params)
            self.assertNotIn("Paris Role", titles, params)

    def test_other_country_filters_still_work(self):
        titles = self._titles("job_search", {"country": "Germany"})
        self.assertEqual(titles, {"Berlin Role"})
        titles = self._titles("job_search", {"country": "France"})
        self.assertEqual(titles, {"Paris Role"})
        titles = self._titles("job_search", {"country": "us"})
        self.assertIn("Atlanta Role", titles)
        self.assertIn("Savannah Role", titles)
        self.assertNotIn("Tbilisi Role", titles)
        self.assertNotIn("Berlin Role", titles)

    def test_v1_country_filter(self):
        country = self._titles("job-list", {"country": "Georgia"})
        self.assertIn("Tbilisi Role", country)
        self.assertNotIn("Atlanta Role", country)
        self.assertNotIn("Berlin Role", country)
        state = self._titles("job-list", {"country": "Georgia (USA)"})
        self.assertIn("Atlanta Role", state)
        self.assertNotIn("Tbilisi Role", state)
        self.assertEqual(self._titles("job-list", {"country": "Germany"}), {"Berlin Role"})
        self.assertEqual(self._titles("job-list", {"city": "Paris"}), {"Paris Role"})


class FetchGeorgiaLocationTests(TestCase):
    def test_fetch_splits_state_and_country(self):
        feed = [
            {
                "title": "Backend Engineer",
                "company": "Local Co",
                "location": "Tbilisi, Georgia",
                "location_country": "Georgia",
                "description": "Build APIs in Tbilisi",
                "apply_url": "https://example.com/tb",
                "posted_at": timezone.now(),
                "platform": "jobs.ge",
                "external_job_id": "fetch-tb",
                "raw": {},
            },
            {
                "title": "Backend Engineer",
                "company": "Local Co",
                "location": "Atlanta, Georgia",
                "location_country": "Georgia",
                "description": "Build APIs",
                "apply_url": "https://example.com/at",
                "posted_at": timezone.now(),
                "platform": "jobs.ge",
                "external_job_id": "fetch-at",
                "raw": {},
            },
            {
                "title": "Backend Engineer",
                "company": "Local Co",
                "location": "Georgia",
                "description": "Build APIs",
                "apply_url": "https://example.com/bare",
                "posted_at": timezone.now(),
                "platform": "jobs.ge",
                "external_job_id": "fetch-bare",
                "raw": {},
            },
        ]
        source = {
            "name": "Jobs.ge IT",
            "platform": "jobs.ge",
            "url": "https://jobs.ge/?cid=6",
            "dynamic_company": True,
        }
        with patch.object(fetch_jobs_cmd, "COMPANIES", [source]), patch.dict(
            fetch_jobs_cmd.PLATFORM_TO_FETCHER, {"jobs.ge": lambda *args, **kwargs: feed}
        ):
            call_command("fetch_jobs", stdout=StringIO())

        tbilisi = Job.objects.get(external_job_id="fetch-tb")
        atlanta = Job.objects.get(external_job_id="fetch-at")
        bare = Job.objects.get(external_job_id="fetch-bare")
        self.assertEqual(tbilisi.location_country, "Georgia")
        self.assertEqual(tbilisi.location, "Tbilisi")
        self.assertIsNone(tbilisi.location_region)
        self.assertEqual(atlanta.location_country, "USA")
        self.assertEqual(atlanta.location_region, "Georgia")
        self.assertEqual(atlanta.location, "Atlanta")
        self.assertEqual(bare.location_country, "Georgia")
        self.assertNotEqual(bare.location_country, atlanta.location_country)
