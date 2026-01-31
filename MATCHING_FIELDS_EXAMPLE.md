# Job Matching Fields: BEFORE and AFTER Normalization

This document shows an example job record before and after the matching fields normalizer is applied.

## Raw Job Data (BEFORE – from fetcher / API)

```json
{
  "title": "Senior Software Engineer - Backend",
  "company": "Acme Corp",
  "location": "San Francisco, CA, USA",
  "description": "We're looking for a Senior Software Engineer to build scalable backend systems.\n\nWhat You'll Do:\n- Design and implement APIs in Python and Go\n- Work with PostgreSQL and Redis\n- Deploy on AWS with Docker and Kubernetes\n\nWhat You'll Bring:\n- 5+ years of software engineering experience\n- Strong Python and Go skills\n- Experience with AWS or GCP\n- Nice to have: React, GraphQL\n\nMust have work authorization. Visa sponsorship not available.\n\nFluent English required. German B2 preferred.",
  "apply_url": "https://acme.com/jobs/123",
  "platform": "greenhouse",
  "external_job_id": "123",
  "posted_at": "2025-01-15T10:00:00Z",
  "raw": {}
}
```

## Normalized Job Record (AFTER – stored in DB)

```json
{
  "title": "Senior Software Engineer - Backend",
  "company": "Acme Corp",
  "location": "San Francisco, CA, USA",

  "work_mode": "unknown",
  "seniority": "senior",
  "role_category": "backend",
  "min_years_experience": 5,

  "skills_required": ["Python", "Go", "PostgreSQL", "Redis", "AWS", "Docker", "Kubernetes", "GCP"],
  "skills_preferred": ["React", "GraphQL"],
  "tech_stack": ["Python", "Go", "PostgreSQL", "Redis", "AWS", "Docker", "Kubernetes", "API"],

  "languages_required": ["English (proficiency not specified)", "German B2"],

  "visa_sponsorship": "no",
  "work_authorization_required": "yes",

  "embedding_text": "Senior Software Engineer - Backend Python Go PostgreSQL Redis AWS Docker Kubernetes GCP React GraphQL English (proficiency not specified) German B2",
  "embedding_vector": null,

  "data_completeness_score": 70,
  "is_low_quality": false,
  "is_duplicate": false,

  "location_country": "USA"
}
```

## Field-by-Field Explanation

| Field | Why It Exists |
|-------|---------------|
| **work_mode** | Structured enum for remote/hybrid/onsite filtering. "unknown" when not detected. |
| **seniority** | Enables experience-based matching (junior vs senior users). |
| **role_category** | Domain matching (frontend, backend, data) for user preferences. |
| **min_years_experience** | Exact numeric filter; NULL when unknown (never 0). |
| **skills_required** | Explicit required skills for hard matching. |
| **skills_preferred** | Nice-to-have skills; separate from required for downranking, not exclusion. |
| **tech_stack** | Broader tech context for semantic/AI matching. |
| **languages_required** | Language + CEFR level for international candidates. |
| **visa_sponsorship** | Critical for non-local candidates; "unknown" when not mentioned. |
| **work_authorization_required** | Legal constraint; "unknown" when not mentioned. |
| **embedding_text** | Input for semantic embedding (title + skills + languages). |
| **embedding_vector** | Vector for similarity search; NULL until embedding service populates it. |
| **data_completeness_score** | 0–100 score; low-quality jobs downranked, not removed. |
| **is_low_quality** | Flag for manual review or exclusion from premium matching. |
| **is_duplicate** | Deduplication flag; jobs not hard-filtered. |
| **location_country** | Normalized country for geo filtering. |

## Matching Safety Rules

- Jobs with missing fields are **never hard-filtered**.
- Unknown enum values use `"unknown"`; unknown numbers use `NULL`.
- Jobs with lower `data_completeness_score` are **downranked**, not removed.
- Unknown fields must not break matching logic.
