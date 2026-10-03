"""Tests for remote + worldwide listing heuristic."""
import unittest

from jobs.remote_worldwide_filter import is_remote_worldwide_listing


class RemoteWorldwideFilterTests(unittest.TestCase):
    def test_plain_remote_rejected(self):
        """Plain 'Remote' is not enough — many are country-locked."""
        self.assertFalse(
            is_remote_worldwide_listing(
                {"location": "Remote", "title": "Engineer", "description": "Build things."}
            )
        )

    def test_remote_worldwide_explicit(self):
        self.assertTrue(
            is_remote_worldwide_listing(
                {
                    "location": "Remote - Worldwide",
                    "title": "Engineer",
                    "description": "",
                }
            )
        )

    def test_remote_us_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Remote - United States",
                    "title": "Engineer",
                    "description": "Work from anywhere in the world.",
                }
            )
        )

    def test_remote_uk_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {"location": "Remote, UK", "title": "Engineer", "description": ""}
            )
        )

    def test_hybrid_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Hybrid - London",
                    "title": "Remote-friendly engineer",
                    "description": "Hybrid role in office. Work from anywhere.",
                }
            )
        )

    def test_onsite_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Berlin, Germany",
                    "title": "On-site engineer",
                    "description": "",
                }
            )
        )

    def test_worldwide_in_description(self):
        self.assertTrue(
            is_remote_worldwide_listing(
                {
                    "location": "Remote",
                    "title": "Engineer",
                    "description": "We hire globally; work from anywhere.",
                }
            )
        )

    def test_us_work_auth_in_description_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Remote",
                    "title": "Engineer",
                    "description": (
                        "Fully remote team. Candidates must be authorized to work in the United States. "
                        "We hire globally within the US."
                    ),
                }
            )
        )

    def test_must_be_located_in_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Remote",
                    "title": "Engineer",
                    "description": "Remote role. Must be located in Canada. Work from anywhere in Canada.",
                }
            )
        )

    def test_work_from_anywhere_accepted(self):
        self.assertTrue(
            is_remote_worldwide_listing(
                {
                    "location": "Remote",
                    "title": "Backend Engineer",
                    "description": "100% remote. Work from anywhere in the world. No geographic restrictions.",
                }
            )
        )

    def test_ashby_workplace_type_remote_with_global(self):
        self.assertTrue(
            is_remote_worldwide_listing(
                {
                    "location": "Remote",
                    "title": "Engineer",
                    "description": "Distributed team hiring globally.",
                    "workplace_type": "Remote",
                }
            )
        )

    def test_city_location_rejected_even_with_global_blurb(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Stockholm",
                    "title": "Cloud Security Engineer",
                    "description": "We are a global company. Work from anywhere when traveling.",
                }
            )
        )

    def test_structured_country_requirement_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Remote",
                    "title": "Engineer",
                    "description": "Work from anywhere in the world.",
                    "workplace_type": "Remote",
                    "applicant_location_requirements": {"@type": "Country", "name": "United States"},
                }
            )
        )

    def test_remote_with_location_country_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Remote",
                    "location_country": "USA",
                    "title": "Engineer",
                    "description": "Work from anywhere in the world.",
                    "workplace_type": "Remote",
                }
            )
        )

    def test_remote_worldwide_location_keeps_country_field(self):
        # Location itself says worldwide — OK even if a country field is empty/absent
        self.assertTrue(
            is_remote_worldwide_listing(
                {
                    "location": "Remote - Worldwide",
                    "title": "Engineer",
                    "description": "",
                }
            )
        )

    def test_remotive_worldwide_location_accepted(self):
        self.assertTrue(
            is_remote_worldwide_listing(
                {
                    "location": "Worldwide",
                    "title": "Backend Engineer",
                    "description": "Build APIs.",
                    "workplace_type": "Remote",
                }
            )
        )

    def test_remotive_usa_only_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "USA",
                    "title": "Backend Engineer",
                    "description": "Remote role for US candidates.",
                    "workplace_type": "Remote",
                }
            )
        )

    def test_emea_only_rejected(self):
        self.assertFalse(
            is_remote_worldwide_listing(
                {
                    "location": "Remote - EMEA",
                    "title": "Engineer",
                    "description": "Work from anywhere.",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
