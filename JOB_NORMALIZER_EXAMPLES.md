# Job Normalizer: 5 Example Raw Jobs and Expected Outputs

## Example 1: Senior Backend Engineer (Python/Django)

**INPUT (raw job):**
```
Title: Senior Backend Engineer
Location: Berlin, Germany
Description:
We're looking for a Senior Backend Engineer to build scalable systems.

Requirements:
- 5+ years of software engineering experience
- Strong Python and Django skills
- PostgreSQL, Redis experience
- Experience with AWS or GCP
- Nice to have: GraphQL, Kubernetes, Docker

Fluent English required. German B2 preferred.
Remote-first, hybrid optional.
```

**EXPECTED OUTPUT:**
```json
{
  "work_mode": "hybrid",
  "seniority": "senior",
  "role_category": "backend",
  "min_years_experience": 5,
  "skills_required": ["Python", "Django", "PostgreSQL", "Redis", "AWS", "Google Cloud"],
  "skills_preferred": ["GraphQL", "Kubernetes", "Docker"],
  "tech_stack": ["Python", "Django", "PostgreSQL", "Redis", "AWS", "Google Cloud", "GraphQL", "Kubernetes", "Docker"],
  "tech_stack_candidates": [],
  "languages_required": ["English (proficiency not specified)", "German B2"],
  "location_country": "Germany",
  "data_completeness_score": 90
}
```

---

## Example 2: Frontend Engineer (React/TypeScript)

**INPUT (raw job):**
```
Title: Frontend Engineer
Location: Remote - USA
Description:
Join our team as a Frontend Engineer. We use React, Next.js, and TypeScript.

What You'll Bring:
- 3+ years with React and TypeScript
- Tailwind CSS, Redux
- Nice to have: Vue.js, Cypress

Tech stack: Node.js, GraphQL, PostgreSQL
```

**EXPECTED OUTPUT:**
```json
{
  "work_mode": "remote",
  "seniority": "unknown",
  "role_category": "frontend",
  "min_years_experience": 3,
  "skills_required": ["React", "Next.js", "TypeScript", "Tailwind CSS", "Redux", "Node.js", "GraphQL", "PostgreSQL"],
  "skills_preferred": ["Vue.js", "Cypress"],
  "tech_stack": ["React", "Next.js", "TypeScript", "Tailwind CSS", "Redux", "Node.js", "GraphQL", "PostgreSQL", "Vue.js", "Cypress"],
  "languages_required": [],
  "location_country": "USA",
  "data_completeness_score": 80
}
```

---

## Example 3: Data Engineer (Spark/Kafka)

**INPUT (raw job):**
```
Title: Data Engineer
Location: London, UK
Description:
Data Engineer needed. ML and data pipelines.

Requirements:
- Spark, Kafka, Airflow
- dbt, BigQuery or Snowflake
- Python, SQL
- TensorFlow or PyTorch nice to have

5+ years experience.
```

**EXPECTED OUTPUT:**
```json
{
  "work_mode": "unknown",
  "seniority": "unknown",
  "role_category": "data",
  "min_years_experience": 5,
  "skills_required": ["Spark", "Kafka", "Airflow", "dbt", "BigQuery", "Python", "SQL"],
  "skills_preferred": ["TensorFlow", "PyTorch"],
  "tech_stack": ["Spark", "Kafka", "Airflow", "dbt", "BigQuery", "Python", "SQL", "TensorFlow", "PyTorch"],
  "languages_required": [],
  "location_country": "United Kingdom",
  "data_completeness_score": 80
}
```

---

## Example 4: Junior Full Stack (.NET/C#)

**INPUT (raw job):**
```
Title: Junior Full Stack Developer
Location: Dublin, Ireland
Description:
Entry-level Full Stack role. We use .NET and C#.

Requirements:
- C#, .NET, ASP.NET Core
- SQL Server
- JavaScript or TypeScript
- Nice to have: React, Azure
```

**EXPECTED OUTPUT:**
```json
{
  "work_mode": "unknown",
  "seniority": "junior",
  "role_category": "fullstack",
  "min_years_experience": null,
  "skills_required": ["C#", ".NET", "SQL Server", "JavaScript", "TypeScript"],
  "skills_preferred": ["React", "Azure"],
  "tech_stack": ["C#", ".NET", "SQL Server", "JavaScript", "TypeScript", "React", "Azure"],
  "languages_required": [],
  "location_country": "Ireland",
  "data_completeness_score": 60
}
```

---

## Example 5: DevOps/SRE (Kubernetes/Terraform)

**INPUT (raw job):**
```
Title: DevOps Engineer
Location: Amsterdam, Netherlands
Description:
Platform Engineer / SRE. On-site or hybrid.

Requirements:
- Docker, Kubernetes (K8s)
- Terraform, Ansible
- CI/CD (GitHub Actions, Jenkins)
- Prometheus, Grafana
- AWS or GCP

5+ years DevOps experience.
```

**EXPECTED OUTPUT:**
```json
{
  "work_mode": "hybrid",
  "seniority": "unknown",
  "role_category": "devops",
  "min_years_experience": 5,
  "skills_required": ["Docker", "Kubernetes", "Terraform", "Ansible", "GitHub Actions", "Jenkins", "Prometheus", "Grafana", "AWS", "Google Cloud"],
  "skills_preferred": [],
  "tech_stack": ["Docker", "Kubernetes", "Terraform", "Ansible", "GitHub Actions", "Jenkins", "Prometheus", "Grafana", "AWS", "Google Cloud"],
  "languages_required": [],
  "location_country": "Netherlands",
  "data_completeness_score": 90
}
```

---

## Notes

- **Exact skill lists** may vary slightly due to section parsing and catalog matching.
- **role_category** is deterministic based on title + skill signals.
- **tech_stack_candidates** appear when tech-like tokens are found that are not in the catalog.
- **data_completeness_score** is 0–100; higher when more fields are populated.
