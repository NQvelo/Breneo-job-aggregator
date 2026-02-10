# Frontend Prompt: Job Filtering and Search

Use this specification to implement filtering and search so that the frontend **correctly and consistently** filters job data from the API.

---

## 1. Primary search endpoint (recommended for full filtering)

**Base URL:** `GET /api/search`

Use this endpoint when you need **multi-value filters** (e.g. multiple countries, multiple job titles, multiple work modes). All multi-value parameters use **comma-separated values** when there are 2 or more items.

### 1.1 Multi-value parameters (comma-separated)

**Rule:** For any parameter that accepts more than one value, **separate values with a comma** in a single query parameter. Do not use spaces after commas when building the URL (or URL-encode if needed).

| Parameter | Example | Meaning |
|-----------|--------|--------|
| `title` | `title=Engineer,Developer,Manager` | Job title contains **any** of these words (OR). |
| `country` | `country=us,uk,de` | Job is in **any** of these countries (codes: us, uk, ca, de, fr, au, in, nl, etc.). |
| `location_country` | `location_country=USA,Germany,United Kingdom` | Job’s normalized country is **any** of these (exact names as stored). |
| `role_category` | `role_category=frontend,backend,data` | Job’s role category is **any** of these. |
| `work_mode` | `work_mode=remote,hybrid,onsite` | Job’s work mode is **any** of these. |
| `seniority` | `seniority=junior,mid,senior` | Job’s seniority is **any** of these. |
| `company` | `company=Stripe,Airbnb,Meta` | Job’s company name contains **any** of these (substring match). |

- **One value:** `country=us` is valid.
- **Two or more values:** always use comma, no spaces: `country=us,uk` (not `country=us&country=uk` unless you explicitly support that alternative).
- **Between different parameters:** use `&`. Example: `title=Engineer,Developer&country=us,uk&work_mode=remote`.

### 1.2 Single-value / text parameters

| Parameter | Values / format | Default |
|-----------|------------------|---------|
| `query` | Natural language search (e.g. `"software engineer"`, `"backend OR frontend"`). Used for title/context. | — |
| `title_filter` | Direct title filter (Google-like syntax). If present, overrides `query`. | — |
| `date_posted` | `all` \| `today` \| `week` \| `month` | `all` |
| `recent` | `true` = only jobs fetched in last 24 hours | false |
| `sort` | `newest` \| `oldest` \| `recently_fetched` | `newest` |

### 1.3 Pagination

Use **one** of these styles:

- **Offset/limit:** `offset=0&limit=20` (limit max 100).
- **Page/size:** `page=1&num_pages=20` (num_pages = page size, max 100).

Do not mix both in the same request.

### 1.4 Building the URL (frontend)

1. **Base:** `https://your-api-domain.com/api/search`
2. **Collect filters:**
   - Multi-value: if the user selected e.g. countries `["us", "uk"]`, set **one** query param: `country=us,uk` (join array with `,`).
   - Same for `title`, `location_country`, `role_category`, `work_mode`, `seniority`, `company`: one param per key, values joined by comma.
3. **Add single-value params:** `query`, `title_filter`, `date_posted`, `recent`, `sort`.
4. **Add pagination:** either `offset` and `limit` or `page` and `num_pages`.
5. **Encode:** use standard URL encoding (e.g. `encodeURIComponent` for each value if building by hand, or use a URL builder that encodes query params).

Example (pseudo):

```text
/api/search?title=Engineer,Developer&country=us,uk&work_mode=remote,hybrid&date_posted=week&sort=newest&page=1&num_pages=20
```

### 1.5 Response shape

```json
{
  "results": [
    {
      "id": 1,
      "title": "...",
      "company": { "id", "name", "domain", "logo", "platform", ... },
      "location": "...",
      "location_country": "USA",
      "work_mode": "remote",
      "seniority": "senior",
      "role_category": "backend",
      "description_short": "...",
      "description": "...",
      "apply_url": "...",
      "posted_at": "...",
      "fetched_at": "...",
      ...
    }
  ],
  "pagination": {
    "offset": null,
    "limit": null,
    "page": 1,
    "num_pages": 20,
    "total_pages": 5,
    "total_results": 99,
    "has_next": true,
    "has_previous": false
  },
  "filters": {
    "query": null,
    "title_filter": null,
    "title": ["Engineer", "Developer"],
    "country": ["us", "uk"],
    "location_country": null,
    "role_category": null,
    "work_mode": ["remote", "hybrid"],
    "seniority": null,
    "company": null,
    "date_posted": "week",
    "recent": false,
    "sort": "newest"
  }
}
```

- **results:** array of job objects (same structure as below).
- **pagination:** use `total_results`, `total_pages`, `has_next`, `has_previous`, and either `page`/`num_pages` or `offset`/`limit` for next/prev.
- **filters:** echo of applied filters; only keys that were sent (or used) are non-null. Use this to show “Active filters” in the UI (e.g. “Country: US, UK”, “Title: Engineer, Developer”).

### 1.6 Filter logic (backend behavior)

- **Across different parameters:** AND. Example: `country=us,uk` AND `work_mode=remote` → job must be in (US or UK) **and** remote.
- **Within the same parameter:** OR. Example: `country=us,uk` → job must be in US **or** UK.
- **Title (`title`):** job’s `title` field must contain **any** of the comma-separated keywords (case-insensitive).
- **Country (`country`):** matched against both raw `location` and normalized `location_country` (with common variations, e.g. us → USA, United States).
- **Company (`company`):** company name substring match (case-insensitive).

---

## 2. Alternative endpoint: list jobs (v1)

**Base URL:** `GET /api/v1/jobs/`

Use for simpler UIs. Supports **single-value** filters only (no multi-value comma-separated list).

| Parameter | Type | Example |
|-----------|------|--------|
| `search` | string | Natural language, same behavior as `query` on `/api/search`. |
| `company` | string | Single company name substring. |
| `location` | string | Single location substring. |
| `work_mode` | string | One of: remote, hybrid, onsite. |
| `seniority` | string | One of: junior, mid, senior, etc. |
| `date_posted` | string | today \| week \| month. |
| `sort` | string | Comma-separated sort fields (e.g. `-posted_at`, `title`). |
| `fields` | string | Comma-separated list of response fields to return. |
| `page` | number | Page number. |
| `limit` | number | Page size (max 100). |

Response includes `results` and `pagination` (structure similar to above, with `current`, `limit`, `total_pages`, `total_items`). No `filters` echo.

---

## 3. Job object fields (for display)

Each item in `results` (from `/api/search` or `/api/v1/jobs/`) typically includes:

- **id**, **title**, **apply_url**
- **company:** object with **id**, **name**, **logo**, **platform**, etc.
- **location**, **location_country**
- **work_mode**, **seniority**, **role_category**
- **description_short** (use in list/cards), **description** (full, for detail)
- **skills_required**, **skills_preferred**, **tech_stack**
- **posted_at**, **fetched_at**
- **responsibilities**, **qualifications**, **benefits** (if needed)

Use **description_short** in tables and cards to keep the UI compact.

---

## 4. UI checklist for “perfect” filtering

1. **Multi-value:** For every filter that can have 2+ options (country, title keywords, role, work mode, seniority, company), send **one** query parameter with values **comma-separated** (e.g. `country=us,uk`).
2. **No spaces in values:** When joining selected values, use no space after comma (e.g. `us,uk` not `us, uk`) unless the API is known to trim.
3. **Encode:** Always URL-encode query parameter values (handled automatically if you use `URLSearchParams` or equivalent).
4. **Pagination:** Stick to one scheme (offset/limit or page/num_pages) and use the same in next/prev requests.
5. **Reflect filters:** Use the `filters` object in the response to show “Active filters” and to pre-fill the form with what was applied.
6. **Empty state:** If no filter is selected for a given key, omit the parameter (do not send `country=` or `title=,,`).
7. **Sort:** Send `sort=newest` (or `oldest`, `recently_fetched`) for `/api/search`; for v1 use `sort=-posted_at` or similar.

---

## 5. Example: full search URL (copy-paste style)

```text
GET /api/search?title=Engineer,Developer&country=us,uk&work_mode=remote,hybrid&seniority=senior,mid&date_posted=week&sort=newest&page=1&num_pages=20
```

This returns jobs that:

- Have “Engineer” or “Developer” in the title, and  
- Are in US or UK, and  
- Are remote or hybrid, and  
- Are senior or mid, and  
- Were posted in the last week,  
sorted by newest first, page 1 with 20 per page.

Use this prompt when implementing or reviewing the frontend so that filtering and search match the API and data is filtered correctly.
