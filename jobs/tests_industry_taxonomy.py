"""
Unit tests for industry taxonomy: determineIndustryTags and helpers.
"""

import unittest

from jobs.industry_taxonomy import (
    INDUSTRY_SOURCE_COMPANY_MAP,
    INDUSTRY_SOURCE_SOURCE,
    INDUSTRY_SOURCE_TITLE_FALLBACK,
    INDUSTRY_SOURCE_UNKNOWN,
    canonicalize_industry_tag,
    determine_industry_tags,
    normalize_text,
)


class TestNormalizeText(unittest.TestCase):
    def test_lowercase_trim(self):
        self.assertEqual(normalize_text("  PayPal  "), "paypal")

    def test_remove_punctuation_and_suffix(self):
        # Punctuation removed; trailing "Inc" stripped per spec
        self.assertEqual(normalize_text("PayPal, Inc."), "paypal")

    def test_strip_company_suffix(self):
        self.assertEqual(normalize_text("PayPal Europe GmbH"), "paypal europe")
        self.assertEqual(normalize_text("Stripe LLC"), "stripe")


class TestCanonicalizeIndustryTag(unittest.TestCase):
    def test_financial_services_to_fintech(self):
        self.assertEqual(canonicalize_industry_tag("Financial Services"), "fintech")

    def test_ecommerce_to_e_commerce(self):
        self.assertEqual(canonicalize_industry_tag("ecommerce"), "e-commerce")


class TestDetermineIndustryTags(unittest.TestCase):
    """Required test cases from spec."""

    def test_1_company_exact_match(self):
        """Company exact match: companyName='PayPal', title='Backend Engineer' => 'fintech, payments' source='company_map'."""
        tags_str, source = determine_industry_tags("PayPal", "Backend Engineer", None)
        self.assertEqual(tags_str, "fintech, payments")
        self.assertEqual(source, INDUSTRY_SOURCE_COMPANY_MAP)

    def test_2_company_with_suffix(self):
        """Company with suffix: companyName='PayPal Europe GmbH', title='Backend Engineer' => 'fintech, payments'."""
        tags_str, source = determine_industry_tags("PayPal Europe GmbH", "Backend Engineer", None)
        self.assertEqual(tags_str, "fintech, payments")
        self.assertEqual(source, INDUSTRY_SOURCE_COMPANY_MAP)

    def test_3_company_multi_industry_disambiguation(self):
        """Company multi-industry with disambiguation: companyName='Amazon', title='AWS DevOps Engineer' => 'cloud'."""
        tags_str, source = determine_industry_tags("Amazon", "AWS DevOps Engineer", None)
        self.assertEqual(tags_str, "cloud")
        self.assertEqual(source, INDUSTRY_SOURCE_COMPANY_MAP)

    def test_4_source_industry_overrides(self):
        """Source industry overrides: sourceIndustry='Financial Services' => 'fintech' source='source'."""
        tags_str, source = determine_industry_tags("Unknown Co", "Engineer", source_industry="Financial Services")
        self.assertEqual(tags_str, "fintech")
        self.assertEqual(source, INDUSTRY_SOURCE_SOURCE)

    def test_5_title_only_fallback_high_confidence(self):
        """Title-only fallback high confidence: companyName='Unknown Startup', title='FinTech Payments Engineer' => 'fintech' (>=2 hits)."""
        tags_str, source = determine_industry_tags("Unknown Startup", "FinTech Payments Engineer", None)
        self.assertEqual(tags_str, "fintech")
        self.assertEqual(source, INDUSTRY_SOURCE_TITLE_FALLBACK)

    def test_6_title_only_low_confidence_empty(self):
        """Title-only low confidence (should NOT guess): companyName='Unknown Startup', title='Software Engineer' => ''."""
        tags_str, source = determine_industry_tags("Unknown Startup", "Software Engineer", None)
        self.assertEqual(tags_str, "")
        self.assertEqual(source, INDUSTRY_SOURCE_UNKNOWN)

    def test_7_tie_case_prefer_empty(self):
        """Tie case: title='Healthcare Education Platform Engineer' => '' (both explicit, prefer unknown)."""
        tags_str, source = determine_industry_tags("Unknown Co", "Healthcare Education Platform Engineer", None)
        self.assertEqual(tags_str, "")
        self.assertEqual(source, INDUSTRY_SOURCE_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
