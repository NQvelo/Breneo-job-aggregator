# API endpoints

**This file describes only the job-aggregator service.** If the frontend also talks to Breneo-api, use two distinct base URLs — see **`docs/frontend-dual-base-url-prompt.txt`**.

Base URL: your deployment origin (e.g. `https://breneo-job-aggregator.up.railway.app`).

- **Human-readable page:** `/` (HTML)
- **Machine-readable index:** `GET /api/overview/` (JSON, same information structured)

OpenAPI: `/api/schema/` · Swagger: `/api/docs/` · ReDoc: `/api/redoc/`

---

## Meta & docs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health/` | Liveness check; returns plain `ok` (no DB). |
| GET | `/api/overview/` | JSON list of all routes (this document, structured). |
| GET | `/api/schema/` | OpenAPI schema. |
| GET | `/api/docs/` | Swagger UI. |
| GET | `/api/redoc/` | ReDoc. |

---

## Jobs (public / legacy)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/` | Active jobs grouped by company. |
| GET | `/api/search` | Search and filter jobs (many query params; see site `/` for filter tables). |
| GET | `/api/job-details` | Job detail by id / external reference (see backend for query params). |
| GET | `/api/v1/jobs/` | Paginated job list (filters, `search`, `sort`, pagination). |
| GET | `/api/v1/jobs/{id}/` | Single job by primary key. |

---

## Companies & industries (public)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/industries/` | List industries (`id`, `name`). |
| GET | `/api/companies` | Company + jobs via query `?name=`. |
| GET | `/api/companies/{company_name}` | Company + jobs; `company_name` is URL-encoded in the path. |

---

## Operations

| Method | Path | Description |
|--------|------|-------------|
| GET, POST | `/api/trigger-fetch` | Runs `fetch_jobs` management command. Optional `secret` query/body if `FETCH_SECRET` is set. |

---

## Employer

**Auth:** `X-Employer-Key: <EMPLOYER_POST_SECRET>` **or** Django session user in group **Employer**.  
Do not expose the secret in browser clients; call from Breneo backend (BFF).

Company **detail / members** routes use the numeric **`company_id`** (primary key) in the path.

| Methods | Path | Description |
|---------|------|-------------|
| GET, POST | `/api/employer/companies` | GET: list (`?search=`, `?external_user_id=` / `staff_user_id`). POST: create company. |
| GET | `/api/employer/companies/for-user` | Companies for a user (`?external_user_id=` required). |
| GET, PUT, PATCH | `/api/employer/companies/{company_id}` | Company detail / full or partial update. Optional `?external_user_id=` for scoped access. |
| POST, DELETE | `/api/employer/companies/{company_id}/members` | Add/remove staff (`external_user_id` in body or query). |
| GET, POST | `/api/employer/staff-memberships` | List (`?company_id=`, `?external_user_id=`). POST: create `{ company_id, external_user_id }`. |
| GET, PUT, PATCH, DELETE | `/api/employer/staff-memberships/{id}` | Membership CRUD by row id. |
| GET, POST | `/api/employer/jobs` | GET: list (`?company_id=` or `?company=`). POST: create job. |
| GET, PATCH, POST, DELETE | `/api/employer/jobs/{job_id}` | Job CRUD; POST mirrors PATCH; optional `?company_id=` to scope. |

---

## Source of truth

The JSON served by **`GET /api/overview/`** is generated from `jobs/api_overview.py` (`API_GROUPS`). Update that module when routes change, then align this markdown if needed.
