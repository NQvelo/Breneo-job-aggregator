"""Tests for legacy search endpoint /api/search (multi-value filters, e.g. two countries)."""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from .models import Job, Company
from .views import _get_multi_value_param
from django.http import HttpRequest


class MultiValueParamTests(TestCase):
    """Test that comma-separated and repeated params are parsed correctly."""

    def test_comma_separated_country(self):
        # Simulate request with ?country=us,uk (getlist returns single element 'us,uk')
        class MockQueryParams:
            def getlist(self, key):
                return ["us,uk"]

            def get(self, key, default=""):
                return "us,uk" if key == "country" else default

            def __contains__(self, key):
                return key == "country"

        request = HttpRequest()
        request.query_params = MockQueryParams()
        result = _get_multi_value_param(request, "country")
        self.assertEqual(result, ["us", "uk"], "country=us,uk should parse to ['us','uk']")

    def test_repeated_country_param(self):
        class MockQueryParams:
            def getlist(self, key):
                return ["us", "uk"] if key == "country" else []

            def get(self, key, default=""):
                return default

            def __contains__(self, key):
                return key == "country"

        request = HttpRequest()
        request.query_params = MockQueryParams()
        result = _get_multi_value_param(request, "country")
        self.assertEqual(result, ["us", "uk"])


class JobSearchTwoCountriesTests(TestCase):
    """Test /api/search with two countries returns jobs from both."""

    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name="Test Co", platform="test")
        # Job in USA (location_country set as by normalizer)
        self.job_us = Job.objects.create(
            title="Engineer in US",
            company=self.company,
            location="New York, NY, USA",
            location_country="USA",
            work_mode="remote",
            seniority="senior",
            posted_at=timezone.now(),
            is_active=True,
            external_job_id="ext-us",
        )
        # Job in UK
        self.job_uk = Job.objects.create(
            title="Developer in UK",
            company=self.company,
            location="London, United Kingdom",
            location_country="United Kingdom",
            work_mode="hybrid",
            seniority="mid",
            posted_at=timezone.now(),
            is_active=True,
            external_job_id="ext-uk",
        )
        # Job in France (should not match country=us,uk)
        self.job_fr = Job.objects.create(
            title="Dev in France",
            company=self.company,
            location="Paris, France",
            location_country="France",
            work_mode="onsite",
            seniority="junior",
            posted_at=timezone.now(),
            is_active=True,
            external_job_id="ext-fr",
        )

    def test_search_two_countries_comma(self):
        url = reverse("job_search")
        response = self.client.get(url, {"country": "us,uk"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        results = response.data.get("results", [])
        self.assertEqual(len(results), 2, "Should return US and UK jobs, got: %s" % [r.get("title") for r in results])
        titles = {r["title"] for r in results}
        self.assertIn("Engineer in US", titles)
        self.assertIn("Developer in UK", titles)
        self.assertNotIn("Dev in France", titles)

    def test_search_two_countries_repeated_param(self):
        url = reverse("job_search") + "?country=us&country=uk"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        results = response.data.get("results", [])
        self.assertEqual(len(results), 2)
        titles = {r["title"] for r in results}
        self.assertIn("Engineer in US", titles)
        self.assertIn("Developer in UK", titles)
