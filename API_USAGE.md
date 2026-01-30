# API Usage Guide

## How to See Newly Fetched Jobs

### Option 1: Search Endpoint with Recent Filter (Recommended)

**Endpoint**: `GET /api/search`

**Query Parameters**:
- `recent=true` - Show only jobs fetched in the last 24 hours
- `sort=recently_fetched` - Sort by most recently fetched first

**Examples**:

1. **See recently fetched jobs** (last 24 hours):
   ```
   GET /api/search?recent=true&sort=recently_fetched
   ```

2. **See recently fetched jobs from today**:
   ```
   GET /api/search?recent=true&date_posted=today&sort=recently_fetched
   ```

3. **See recently fetched jobs with pagination**:
   ```
   GET /api/search?recent=true&sort=recently_fetched&page=1&num_pages=20
   ```

4. **See recently fetched jobs from this week**:
   ```
   GET /api/search?recent=true&date_posted=week&sort=recently_fetched
   ```

### Option 2: Main Endpoint (All Jobs Grouped by Company)

**Endpoint**: `GET /api/`

Returns all active jobs grouped by company, ordered by most recently posted/fetched.

**Example**:
```
GET /api/
```

### Option 3: Search Endpoint (All Jobs with Sorting)

**Endpoint**: `GET /api/search`

**Sort Options**:
- `sort=newest` - Sort by posted_at (newest first) - **Default**
- `sort=recently_fetched` - Sort by fetched_at (most recently fetched first)
- `sort=oldest` - Sort by posted_at (oldest first)

**Examples**:

1. **All jobs sorted by most recently fetched**:
   ```
   GET /api/search?sort=recently_fetched
   ```

2. **Recent jobs from this week**:
   ```
   GET /api/search?date_posted=week&sort=recently_fetched&recent=true
   ```

3. **Search with recent filter**:
   ```
   GET /api/search?query=software engineer&recent=true&sort=recently_fetched
   ```

## Complete API Reference

### 1. Jobs Grouped by Company
```
GET /api/
```
Returns all active jobs grouped by company.

**Response**: Array of companies with nested jobs

---

### 2. Job Search (Recommended for New Jobs)
```
GET /api/search
```

**Query Parameters**:
- `recent=true` - Filter: Show only jobs fetched in last 24 hours
- `sort=recently_fetched` - Sort by most recently fetched
- `sort=newest` - Sort by posted date (default)
- `sort=oldest` - Sort by oldest posted date
- `date_posted=today|week|month|all` - Filter by posted date
- `query="software engineer"` - Search query
- `country=us` - Filter by country
- `page=1` - Page number
- `num_pages=20` - Results per page
- `offset=0` - Offset for pagination
- `limit=20` - Results per page (alternative to num_pages)

**Examples**:
```bash
# See recently fetched jobs
curl "https://your-app.onrender.com/api/search?recent=true&sort=recently_fetched"

# See new jobs from today
curl "https://your-app.onrender.com/api/search?date_posted=today&sort=recently_fetched"

# See recent jobs with pagination
curl "https://your-app.onrender.com/api/search?recent=true&page=1&num_pages=50"

# Search recent jobs
curl "https://your-app.onrender.com/api/search?query=engineer&recent=true&sort=recently_fetched"
```

---

### 3. Job Details
```
GET /api/job-details?job_id=123
```

---

### 4. Company Details
```
GET /api/companies?name=Xometry
GET /api/companies/Xometry
```

---

### 5. Trigger Job Fetch
```
GET /api/trigger-fetch?secret=YOUR_SECRET
POST /api/trigger-fetch
```

Triggers job fetching manually.

## Sorting by Recently Fetched

The `sort=recently_fetched` parameter sorts jobs by `fetched_at` timestamp, showing the most recently fetched jobs first. This is useful to see:
- Jobs that were just added to the database
- Recently updated job information
- Latest job listings

## Filtering Recent Jobs

The `recent=true` parameter filters to show only jobs fetched in the last 24 hours. Combine with sorting for best results:

```
GET /api/search?recent=true&sort=recently_fetched
```

This will show:
- Only jobs fetched in the last 24 hours
- Sorted by most recently fetched first

## Response Format

```json
{
  "results": [
    {
      "id": 123,
      "title": "Software Engineer",
      "company": {...},
      "location": "Remote",
      "description": "...",
      "responsibilities": "...",
      "qualifications": "...",
      "benefits": "...",
      "posted_at": "2026-01-15T00:00:00Z",
      "fetched_at": "2026-01-15T14:30:00Z",
      ...
    }
  ],
  "pagination": {
    "page": 1,
    "num_pages": 20,
    "total_pages": 5,
    "total_results": 100,
    "has_next": true,
    "has_previous": false
  },
  "filters": {
    "recent": true,
    "sort": "recently_fetched",
    ...
  }
}
```
