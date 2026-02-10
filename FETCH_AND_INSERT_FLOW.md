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

### 5.1 Industry matching (industryTags)

You are working on the Breneo job aggregator backend.

**Task:** Implement logic that determines and stores the `industryTags` field for each job during ingestion.

**Important:**

- Only implement **industry** logic (no changes to skills, seniority, etc.).
- Industry must be **deterministic and explainable**.
- Never invent industries with low confidence – if unsure, leave empty.

#### 5.1.1 Job field

Jobs table already contains:

- `industryTags`: string (comma-separated canonical tags), e.g.:
  - `"fintech, banking"`
  - `"e-commerce, retail"`

Rules for tags:

- lowercase
- canonical (no synonyms)
- deduplicated
- sorted alphabetically

If no industry can be determined, leave `industryTags` empty / null.

#### 5.1.2 Determination priority

Industry is determined in this **exact order**:

**Step 1 – Source-provided industry (highest priority)**

If the job source API provides an `industry` / `category` / `sector` field:

- normalize it using `INDUSTRY_SYNONYMS` (see below)
- store canonical tag(s) into `industryTags`
- **stop** (no further inference)

**Step 2 – Company industry map (primary logic)**

Use a deterministic company-to-industry mapping:

- `COMPANY_INDUSTRY_MAP: Record<string, string[]>`

Example:

```text
{
  "paypal": ["fintech","payments"],
  "stripe": ["fintech","payments"],
  "amazon": ["e-commerce","retail","cloud"],
  "sap": ["enterprise software","saas"],
  "siemens": ["industrial","engineering"],
  "zalando": ["e-commerce","retail"]
}
```

Process:

- normalize `companyName`:
  - lowercase
  - trim
  - remove punctuation
- lookup in `COMPANY_INDUSTRY_MAP`
- if found:
  - use those tags
  - **stop**

**Step 3 – High-confidence keyword inference (fallback)**

Only used if:

- no industry from source, and
- no company match.

Create:

- `KEYWORD_INDUSTRY_MAP: Record<string, string[]>`

Example:

```text
{
  "fintech": ["payment","bank","card","lending","kyc","aml","trading"],
  "e-commerce": ["checkout","cart","order","storefront","marketplace","shop"],
  "healthcare": ["patient","clinical","hospital","ehr","medical"],
  "gaming": ["game","unity","unreal","multiplayer","gaming"],
  "education": ["student","learning","edtech","course","academy"],
  "logistics": ["delivery","warehouse","fleet","logistics","shipment"]
}
```

Inference rules:

- combine `title` + `descriptionRaw` into one text block
- lowercase it
- for each industry:
  - count how many keywords appear
- assign an industry **only if**:
  - `keywordCount >= 2`, **or**
  - title contains the industry name explicitly

If no industry meets the rule, leave `industryTags` empty.

#### 5.1.3 Synonym normalization

Create:

- `INDUSTRY_SYNONYMS: Record<string, string>`

Example:

```text
{
  "financial services": "fintech",
  "banking": "banking",
  "payments": "payments",
  "ecommerce": "e-commerce",
  "retail tech": "retail",
  "health tech": "healthcare",
  "medtech": "healthcare",
  "edtech": "education",
  "saas": "saas",
  "enterprise software": "enterprise software"
}
```

When receiving any industry text:

- lowercase
- trim
- map via `INDUSTRY_SYNONYMS`
- if not found, keep the cleaned value as-is

#### 5.1.4 Final formatting

Before saving:

- deduplicate tags
- sort alphabetically
- join with comma and space

Example:

- `["payments","fintech","banking"]`
- → `["banking","fintech","payments"]`
- → `"banking, fintech, payments"`

If the array is empty, store null / empty string (consistent with the current schema).

#### 5.1.5 Integration into fetch/upsert flow

In the job ingestion / upsert pipeline, **after** mapping raw job fields:

1. Call:

   - `industryTags = determineIndustry({ title, descriptionRaw, companyName, sourceIndustryField })`

2. Set:

   - `job.industryTags = industryTags`

3. Continue normal upsert.

Only regenerate `industryTags` if:

- job is new, or
- `companyName` changed, or
- `title` or `description` changed, or
- `industryTags` is currently empty.

#### 5.1.6 Test cases (examples)

- Case 1: `company = "PayPal"` → `industryTags = "fintech, payments"`
- Case 2: `company = unknown`, `title = "Senior FinTech Backend Engineer"` → `industryTags = "fintech"`
- Case 3: `company = unknown`, description contains `"checkout"` and `"order management"` → `industryTags = "e-commerce"`
- Case 4: `company = unknown`, very generic text → `industryTags = ""` (empty)
- Case 5: source provides `"Financial Services"` → `industryTags = "fintech"`


So every fetched job (new or updated) gets these matching fields filled from the normalizer.

## 6. Summary – “every detail” on fetch

- **From API**: title, company, location, description, apply_url, posted_at, platform, external_job_id, raw → all passed into `update_or_create` and/or used for Company.
- **From parser**: responsibilities, qualifications, workplace_type, skills_required (legacy), structured_description (summary, company_overview, role_description), benefits → set in Job.save() and again explicitly in fetch_jobs.
- **From normalizer**: work_mode, seniority, role_category, min_years_experience, skills_required (catalog), skills_preferred, tech_stack, tech_stack_candidates, languages_required, embedding_text, data_completeness_score, location_country, visa_sponsorship, work_authorization_required → set in fetch_jobs for every job that has title and description/qualifications.

So when you fetch new jobs, every available detail from the fetcher is inserted, and every derived field (parser + normalizer) is refreshed for that run.
