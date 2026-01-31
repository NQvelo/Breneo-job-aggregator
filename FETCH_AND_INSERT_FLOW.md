# Job fetch and insert flow – what gets fetched and stored

When you run `python manage.py fetch_jobs`, this is what happens for each job.

## 1. Fetchers return (per job dict)

| Field from API / source | Fetcher key | Example sources |
|-------------------------|-------------|------------------|
| Title | `title` | Greenhouse `job.title`, Lever `job.text`, RSS `entry.title` |
| Company name | `company` | Passed in (COMPANIES config) |
| Location | `location` | Greenhouse `job.location.name`, Lever `job.categories.location` |
| Description (raw HTML → plain text) | `description` | Greenhouse `job.content`, Lever `job.description`, RSS `entry.description` |
| Apply URL | `apply_url` | Greenhouse `absolute_url`, Lever `hostedUrl`, RSS `entry.link` |
| Posted date | `posted_at` | Greenhouse `first_published` / `updated_at`, Lever `postDate`, RSS `published` |
| Platform | `platform` | `"greenhouse"`, `"lever"`, `"rss"`, etc. |
| External job ID | `external_job_id` | Greenhouse `job.id`, Lever `job.id`, RSS link |
| Raw API payload | `raw` | Full response object for debugging |

Some fetchers (e.g. career_page, jobs.ge) may return `location=None`, `description=None`, or `posted_at=None` when the source does not provide them.

## 2. fetch_jobs → update_or_create defaults

These values from the fetcher are written to the DB on create/update:

| Fetcher field | Job model field | Notes |
|---------------|-----------------|--------|
| `title` | `title` | Required |
| `company` | `company` (FK) | Resolved to Company instance |
| `location` | `location` | Can be null |
| `description` | `description` | Raw/plain text |
| `apply_url` | `apply_url` | Fallback: `external_job_id` |
| `posted_at` | `posted_at` | Parsed via `parse_date()` |
| `raw` | `raw` | Full payload |
| — | `is_active` | Set to `True` |
| `platform` | `platform` | From company/config |
| `external_job_id` | `external_job_id` | Unique with platform |

Logo is not stored on Job; it is on Company and set when the company is created/updated.

## 3. Job.save() (on create/update)

Runs when the job is first saved (from `update_or_create`):

| What runs | Fields set |
|-----------|------------|
| HTML clean | `description` (plain text) |
| Raw `first_published` | `posted_at` if missing |
| Job posting parser | `responsibilities`, `qualifications`, `workplace_type`, `skills_required` (legacy), `structured_description["summary"]` |
| process_job_description | `benefits`, `structured_description` (company_overview, role_description) |
| Job normalizer (if new or derived empty) | See “Matching fields” below |

## 4. fetch_jobs after save – parser + benefits

For each job, the command then runs:

- `parse_job_posting_for_db(description, location)` →  
  `responsibilities`, `qualifications`, `workplace_type`, `skills_required`, `structured_description["summary"]`
- `process_job_description(description)` →  
  `benefits`, `structured_description` (company_overview, role_description)

So parsed sections and short summary are always refreshed for every fetched job.

## 5. fetch_jobs after save – matching fields (every fetch)

For every job that has `title` and (`description` or `qualifications`), the command runs:

`normalize_job_fields(title, description_raw, location, qualifications_text)` and then updates and saves:

| Normalizer output | Job model field |
|-------------------|-----------------|
| work_mode | `work_mode` |
| seniority | `seniority` |
| role_category | `role_category` |
| min_years_experience | `min_years_experience` |
| skills_required | `skills_required` (catalog-based) |
| skills_preferred | `skills_preferred` |
| tech_stack | `tech_stack` |
| tech_stack_candidates | `tech_stack_candidates` |
| languages_required | `languages_required` |
| embedding_text | `embedding_text` |
| data_completeness_score | `data_completeness_score` |
| location_country | `location_country` |
| visa_sponsorship | `visa_sponsorship` |
| work_authorization_required | `work_authorization_required` |

So every fetched job (new or updated) gets these matching fields filled from the normalizer.

## 6. Summary – “every detail” on fetch

- **From API**: title, company, location, description, apply_url, posted_at, platform, external_job_id, raw → all passed into `update_or_create` and/or used for Company.
- **From parser**: responsibilities, qualifications, workplace_type, skills_required (legacy), structured_description (summary, company_overview, role_description), benefits → set in Job.save() and again explicitly in fetch_jobs.
- **From normalizer**: work_mode, seniority, role_category, min_years_experience, skills_required (catalog), skills_preferred, tech_stack, tech_stack_candidates, languages_required, embedding_text, data_completeness_score, location_country, visa_sponsorship, work_authorization_required → set in fetch_jobs for every job that has title and description/qualifications.

So when you fetch new jobs, every available detail from the fetcher is inserted, and every derived field (parser + normalizer) is refreshed for that run.
