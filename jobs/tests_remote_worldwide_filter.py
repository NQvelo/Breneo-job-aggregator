"""Tests for remote + worldwide listing heuristic."""
import unittest

from jobs.remote_worldwide_filter import is_remote_worldwide_listing


class RemoteWorldwideFilterTests(unittest.TestCase):
    def test_plain_remote(self):
        self.assertTrue(
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
                    "description": "",
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
                    "description": "Hybrid role in office.",
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


if __name__ == "__main__":
    unittest.main()
