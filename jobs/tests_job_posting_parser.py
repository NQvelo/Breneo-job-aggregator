"""Tests for job_posting_parser (incl. non-English section headings)."""

from django.test import TestCase

from jobs.job_posting_parser import parse_job_posting_for_db


class GeorgianJobPostingParserTests(TestCase):
    def test_splits_role_and_requirements_sections(self):
        text = """
შენი როლი თინეთში:

** Back-end სტანდარტების დაცვა;

** PHP-ზე სუფთა კოდის წერა;

ეს ვაკანსია შენთვისაა, თუ გაქვს:

** მინიმუმ 4 წლიანი გამოცდილება;

** PHP-ის სიღრმისეული ცოდნა და პრაქტიკული გამოცდილება;

თინეთში დაგხვდება:

** ჯანმრთელობის დაზღვევა;
"""
        out = parse_job_posting_for_db(text)
        self.assertIn("Back-end", out["responsibilities"])
        self.assertIn("PHP-ზე", out["responsibilities"])
        self.assertIn("4 წლიანი", out["qualifications"])
        self.assertIn("PHP-ის", out["qualifications"])
        self.assertGreaterEqual(len([ln for ln in out["qualifications"].split("\n") if ln.strip()]), 2)
        self.assertNotIn("დაზღვევა", out["responsibilities"])
        self.assertNotIn("დაზღვევა", out["qualifications"])
