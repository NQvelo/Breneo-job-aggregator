"""
Tests for Breneo job parsing + matching pipeline.

- 30+ skill extraction cases (including .NET, Node.js, C#/C++/C)
- 15+ roleCategory inference cases
"""

import unittest
from jobs.job_normalizer import (
    extract_skills,
    extract_work_mode,
    extract_seniority,
    infer_role_category,
    normalize_job_fields,
    parse_stored_location_fields,
    get_skill_alias_index,
)


# --- Skill extraction tests ---
class TestSkillExtraction(unittest.TestCase):
    def test_dotnet_extraction(self):
        r = extract_skills("We use .NET and ASP.NET Core.", "Backend Engineer")
        self.assertIn(".NET", r["required"])
        self.assertIn(".NET", r["techStack"])

    def test_nodejs_extraction(self):
        r = extract_skills("Experience with Node.js and node required.", "Full Stack")
        self.assertIn("Node.js", r["required"])

    def test_csharp_extraction(self):
        r = extract_skills("Proficiency in C# and CSharp required.", "Software Engineer")
        self.assertIn("C#", r["required"])

    def test_cpp_extraction(self):
        r = extract_skills("Must know C++ or cpp.", "Systems Engineer")
        self.assertIn("C++", r["required"])

    def test_c_vs_cpp_vs_csharp(self):
        # Longest match first: C++ and C# before C
        r = extract_skills("We use C, C++, and C#.", "Engineer")
        self.assertIn("C", r["required"])
        self.assertIn("C++", r["required"])
        self.assertIn("C#", r["required"])

    def test_postgresql_aliases(self):
        r = extract_skills("PostgreSQL and postgres experience.", "Backend")
        self.assertIn("PostgreSQL", r["required"])

    def test_javascript_aliases(self):
        r = extract_skills("JavaScript, JS, and TypeScript.", "Frontend")
        self.assertIn("JavaScript", r["required"])
        self.assertIn("TypeScript", r["required"])

    def test_react_nextjs(self):
        r = extract_skills("React and Next.js for the frontend.", "Frontend Engineer")
        self.assertIn("React", r["required"])
        self.assertIn("Next.js", r["required"])

    def test_vuejs_variants(self):
        r = extract_skills("Vue.js, vuejs, or Vue.", "Frontend")
        self.assertIn("Vue.js", r["required"])

    def test_python_django_flask(self):
        r = extract_skills("Python, Django, Flask, FastAPI.", "Backend")
        self.assertIn("Python", r["required"])
        self.assertIn("Django", r["required"])
        self.assertIn("Flask", r["required"])
        self.assertIn("FastAPI", r["required"])

    def test_aws_gcp_azure(self):
        r = extract_skills("AWS, GCP, or Azure cloud experience.", "DevOps")
        self.assertIn("AWS", r["required"])
        self.assertTrue("Google Cloud" in r["required"] or "GCP" in r["required"])
        self.assertIn("Azure", r["required"])

    def test_docker_kubernetes(self):
        r = extract_skills("Docker and Kubernetes (K8s).", "SRE")
        self.assertIn("Docker", r["required"])
        self.assertIn("Kubernetes", r["required"])

    def test_section_required_vs_preferred(self):
        text = """
        Requirements:
        - Python, React, SQL
        Nice to have:
        - GraphQL, Redis
        """
        r = extract_skills(text, "Engineer")
        self.assertIn("Python", r["required"])
        self.assertIn("React", r["required"])
        self.assertIn("SQL", r["required"])
        self.assertIn("GraphQL", r["preferred"])
        self.assertIn("Redis", r["preferred"])
        self.assertIn("GraphQL", r["techStack"])
        self.assertIn("Redis", r["techStack"])

    def test_tech_stack_section(self):
        text = """
        Tech stack:
        - Node.js, PostgreSQL, Redis
        """
        r = extract_skills(text, "Backend")
        self.assertIn("Node.js", r["techStack"])
        self.assertIn("PostgreSQL", r["techStack"])
        self.assertIn("Redis", r["techStack"])

    def test_fallback_no_sections(self):
        text = "We need Python and Go. Experience with Docker."
        r = extract_skills(text, "Engineer")
        self.assertIn("Python", r["required"])
        self.assertIn("Go", r["required"])
        self.assertIn("Docker", r["required"])
        self.assertTrue(r["usedFallbackSectioning"])

    def test_empty_input(self):
        r = extract_skills("", None)
        self.assertEqual(r["required"], [])
        self.assertEqual(r["preferred"], [])
        self.assertEqual(r["techStack"], [])
        self.assertTrue(r["usedFallbackSectioning"])

    def test_mongodb_elasticsearch(self):
        r = extract_skills("MongoDB and Elasticsearch.", "Data Engineer")
        self.assertIn("MongoDB", r["required"])
        self.assertIn("Elasticsearch", r["required"])

    def test_tensorflow_pytorch(self):
        r = extract_skills("TensorFlow or PyTorch for ML.", "ML Engineer")
        self.assertIn("TensorFlow", r["required"])
        self.assertIn("PyTorch", r["required"])

    def test_ruby_rails(self):
        r = extract_skills("Ruby on Rails experience.", "Backend")
        self.assertIn("Ruby on Rails", r["required"])

    def test_spring_java(self):
        r = extract_skills("Java and Spring Boot.", "Backend")
        self.assertIn("Java", r["required"])
        self.assertIn("Spring Boot", r["required"])

    def test_cypress_playwright(self):
        r = extract_skills("Cypress or Playwright for E2E.", "QA")
        self.assertIn("Cypress", r["required"])
        self.assertIn("Playwright", r["required"])

    def test_figma_design(self):
        r = extract_skills("Figma and design systems.", "Designer")
        self.assertIn("Figma", r["required"])

    def test_terraform_ansible(self):
        r = extract_skills("Terraform, Ansible for IaC.", "DevOps")
        self.assertIn("Terraform", r["required"])
        self.assertIn("Ansible", r["required"])

    def test_airflow_kafka_spark(self):
        r = extract_skills("Airflow, Kafka, Spark for data pipelines.", "Data Engineer")
        self.assertIn("Airflow", r["required"])
        self.assertIn("Kafka", r["required"])
        self.assertIn("Spark", r["required"])

    def test_swift_kotlin_mobile(self):
        r = extract_skills("Swift or Kotlin for mobile.", "Mobile Engineer")
        self.assertIn("Swift", r["required"])
        self.assertIn("Kotlin", r["required"])

    def test_oauth_jwt_security(self):
        r = extract_skills("OAuth, JWT, OIDC for auth.", "Security Engineer")
        self.assertIn("OAuth", r["required"])
        self.assertIn("JWT", r["required"])

    def test_skill_alias_index(self):
        idx = get_skill_alias_index()
        self.assertIn("python", idx)
        self.assertEqual(idx["python"], "Python")
        self.assertIn("nodejs", idx)
        self.assertIn("csharp", idx)
        self.assertEqual(idx["csharp"], "C#")


# --- Role category inference tests ---
class TestRoleCategoryInference(unittest.TestCase):
    def test_frontend_from_title(self):
        r = infer_role_category("Frontend Engineer", ["HTML"], [], [])
        self.assertEqual(r, "frontend")

    def test_frontend_from_skills(self):
        r = infer_role_category("Software Engineer", ["React", "Vue.js"], [], [])
        self.assertEqual(r, "frontend")

    def test_backend_from_title(self):
        r = infer_role_category("Backend Engineer", [], [], [])
        self.assertEqual(r, "backend")

    def test_backend_from_skills(self):
        r = infer_role_category("Engineer", ["Node.js", "Django"], [], [])
        self.assertEqual(r, "backend")

    def test_fullstack_from_title(self):
        r = infer_role_category("Full Stack Developer", [], [], [])
        self.assertEqual(r, "fullstack")

    def test_fullstack_from_both_signals(self):
        r = infer_role_category("Engineer", ["React", "Node.js", "Django"], [], [])
        self.assertEqual(r, "fullstack")

    def test_data_from_title(self):
        r = infer_role_category("Data Engineer", [], [], [])
        self.assertEqual(r, "data")

    def test_data_from_skills(self):
        r = infer_role_category("Engineer", ["Spark", "Kafka", "Airflow"], [], [])
        self.assertEqual(r, "data")

    def test_devops_from_title(self):
        r = infer_role_category("DevOps Engineer", [], [], [])
        self.assertEqual(r, "devops")

    def test_devops_from_skills(self):
        r = infer_role_category("Engineer", ["Docker", "Kubernetes", "Terraform"], [], [])
        self.assertEqual(r, "devops")

    def test_mobile_from_title(self):
        r = infer_role_category("Mobile Engineer", [], [], [])
        self.assertEqual(r, "mobile")

    def test_mobile_from_skills(self):
        r = infer_role_category("Engineer", ["React Native", "Flutter"], [], [])
        self.assertEqual(r, "mobile")

    def test_qa_from_title(self):
        r = infer_role_category("QA Engineer", [], [], [])
        self.assertEqual(r, "qa")

    def test_qa_from_skills(self):
        r = infer_role_category("Engineer", ["Cypress", "Playwright", "Selenium"], [], [])
        self.assertEqual(r, "qa")

    def test_security_from_title(self):
        r = infer_role_category("Security Engineer", [], [], [])
        self.assertEqual(r, "security")

    def test_security_from_skills(self):
        r = infer_role_category("Engineer", ["OWASP", "SAML", "OIDC"], [], [])
        self.assertEqual(r, "security")

    def test_design_from_title(self):
        r = infer_role_category("UI/UX Designer", [], [], [])
        self.assertEqual(r, "design")

    def test_design_from_skills(self):
        r = infer_role_category("Designer", ["Figma", "Sketch"], [], [])
        self.assertEqual(r, "design")

    def test_product_from_title(self):
        r = infer_role_category("Product Manager", [], [], [])
        self.assertEqual(r, "product")


# --- Work mode tests ---
class TestWorkMode(unittest.TestCase):
    def test_remote(self):
        self.assertEqual(extract_work_mode("Work remotely", "Engineer", None), "remote")
        self.assertEqual(extract_work_mode("WFH", None, None), "remote")

    def test_hybrid(self):
        self.assertEqual(extract_work_mode("Hybrid role", "Engineer", None), "hybrid")

    def test_onsite(self):
        self.assertEqual(extract_work_mode("On-site required", "Engineer", None), "onsite")

    def test_unknown(self):
        self.assertEqual(extract_work_mode("", None, None), "unknown")


# --- Seniority tests ---
class TestSeniority(unittest.TestCase):
    def test_intern(self):
        self.assertEqual(extract_seniority("Intern", ""), "intern")

    def test_junior(self):
        self.assertEqual(extract_seniority("Junior Developer", ""), "junior")
        self.assertEqual(extract_seniority("Entry-level", ""), "junior")

    def test_mid(self):
        self.assertEqual(extract_seniority("Mid-level Engineer", ""), "mid")

    def test_senior(self):
        self.assertEqual(extract_seniority("Senior Engineer", ""), "senior")

    def test_lead(self):
        self.assertEqual(extract_seniority("Staff Engineer", ""), "lead")
        self.assertEqual(extract_seniority("Principal Engineer", ""), "lead")

    def test_most_senior_wins(self):
        self.assertEqual(extract_seniority("Junior to Senior Engineer", ""), "senior")


# --- Full normalize tests ---
class TestNormalizeJobFields(unittest.TestCase):
    def test_full_normalization(self):
        r = normalize_job_fields(
            title="Senior Backend Engineer",
            description_raw="""
            We're looking for a Senior Backend Engineer. 5+ years experience.
            Requirements: Python, Django, PostgreSQL, Redis.
            Nice to have: GraphQL, Kubernetes.
            Fluent English required.
            """,
            location="Berlin, Germany",
        )
        self.assertIn(r["work_mode"], ("unknown", "remote", "hybrid", "onsite"))
        self.assertEqual(r["seniority"], "senior")
        self.assertEqual(r["role_category"], "backend")
        self.assertEqual(r["min_years_experience"], 5)
        self.assertIn("Python", r["skills_required"])
        self.assertIn("Django", r["skills_required"])
        self.assertIn("GraphQL", r["skills_preferred"])
        self.assertEqual(r["location_country"], "Germany")
        self.assertEqual(r.get("canonical_location"), "Berlin")
        self.assertGreater(r["data_completeness_score"], 0)


class TestParseStoredLocationFields(unittest.TestCase):
    def test_multi_us_cities_semicolon(self):
        city, country = parse_stored_location_fields("Chicago, IL; New York, NY")
        self.assertEqual(city, "Chicago")
        self.assertEqual(country, "USA")

    def test_single_us_city_state(self):
        self.assertEqual(
            parse_stored_location_fields("San Francisco, CA"),
            ("San Francisco", "USA"),
        )

    def test_canada_province(self):
        self.assertEqual(
            parse_stored_location_fields("Toronto, ON"),
            ("Toronto", "Canada"),
        )

    def test_europe_city_country(self):
        self.assertEqual(
            parse_stored_location_fields("Berlin, Germany"),
            ("Berlin", "Germany"),
        )

    def test_london_england_to_uk(self):
        self.assertEqual(
            parse_stored_location_fields("London, England"),
            ("London", "United Kingdom"),
        )

    def test_edinburgh_scotland(self):
        self.assertEqual(
            parse_stored_location_fields("Edinburgh, Scotland"),
            ("Edinburgh", "United Kingdom"),
        )

    def test_new_england_region_not_uk_country(self):
        """Regional phrase must not be parsed as country England."""
        city, country = parse_stored_location_fields("Boston, New England")
        self.assertEqual(city, "Boston, New England")
        self.assertIsNone(country)

    def test_empty(self):
        self.assertEqual(parse_stored_location_fields(None), (None, None))
        self.assertEqual(parse_stored_location_fields(""), (None, None))
        self.assertEqual(parse_stored_location_fields("   "), (None, None))


if __name__ == "__main__":
    unittest.main()
