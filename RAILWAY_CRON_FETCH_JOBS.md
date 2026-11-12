# Railway: Daily cron for job data updates (`fetch_jobs`)

Fetched jobs (Georgian boards jobs.ge, hr.ge, myjobs.ge, jobs.ss.ge; Greenhouse, Lever, Ashby,
Workable, SmartRecruiters, Workday, iCIMS, Remotive, We Work Remotely) are refreshed **once a day** by a
**separate Railway Cron service**. Employer-posted jobs (`platform="employer"`) are created
instantly through the API and are never modified or deleted by `fetch_jobs`.

There is no HTTP trigger endpoint; the cron service runs the management command directly.

---

## 1. Web service (no change)

There is no `railway.toml`; all Railway settings are managed in the dashboard.
The web service uses the `Procfile` unless a Custom Start Command is set in its settings.
Do **not** use the cron command as the web service start command.

---

## 2. Cron service for `fetch_jobs`

1. In the Railway project, click **New** → **Empty Service** (or duplicate the web service).
2. Connect it to the **same GitHub repo** (Breneo-job-aggregator), same branch.
3. **Settings** for this service:
   - **Config-as-code path:** leave empty.
   - **Custom Start Command** (required — without it the `Procfile` starts Gunicorn and the run never exits):
     ```bash
     python manage.py migrate --noinput && python manage.py fetch_jobs && python manage.py enrich_jobs_ai
     ```
   - **Cron Schedule:** `45 20 * * *` — every day at 20:45 UTC = **00:45 Georgia time (UTC+4)**.
   - **Restart Policy:** `Never` (a cron run must exit; it must not be restarted in a loop).
4. **Variables:** reference the same variables as the web service — at minimum `DATABASE_URL`
   (link the Postgres service), `GROQ_API_KEY` and `GEMINI_API_KEY` for AI summaries. Without either
   key `enrich_jobs_ai` skips and jobs keep the rule-based fields. Optional:
   - `GROQ_ENRICHMENT_MODELS` — comma-separated Groq models to rotate
     (default `openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b`), `GROQ_ENRICHMENT_TPM` (default 8000).
   - `GEMINI_MODEL` / `GEMINI_ENRICHMENT_MODEL` (default `gemini-2.5-flash`).
   - `AI_MAX_INPUT_TOKENS` (posting text per job, default 1500), `AI_ENRICH_MAX_PER_RUN` (default 1500),
     `AI_ENRICH_WORKERS` (default 3 parallel requests).
5. Deploy. Then open the service → **Deployments** and check the logs of the next run.

If a run is still active when the next one is due, Railway skips the new run.

---

## 3. What a run does

1. Fetches every source in `COMPANIES` (`jobs/management/commands/fetch_jobs.py`).
   - **Georgian boards** (jobs.ge, hr.ge, myjobs.ge, jobs.ss.ge) are read from every board category that
     matches the role families below (category IDs are listed in `jobs/fetchers.py`). Onsite jobs in Georgia
     are kept. An ad cross-posted on several boards is kept once, preferring jobs.ge.
   - **All other sources** keep a job only if it is remote **and open worldwide** (an explicit
     worldwide / anywhere signal and no country or region lock), and its title falls in one of the 16 role
     families in `jobs/role_categories.py`: software engineering, DevOps & cloud, data & AI, design, product
     & business analysis, project & program management, marketing, sales & success, finance & accounting,
     HR & recruiting, customer support, operations & admin, healthcare, education, engineering & trades,
     writing & media. `fetch_jobs --allow-region-remote` also keeps region-limited remote jobs ("Remote - US").
   - jobs.ge is requested at most once every 5 seconds (its robots.txt `Crawl-delay`). Only listings not yet
     stored have their detail page opened, at most 600 per run (`JOBS_GE_MAX_DETAIL_FETCHES`, about 50
     minutes); the rest are picked up on later runs. jobs.ge has several thousand listings in these
     categories, so the first few runs are long (about 1.5 hours) until the backlog is stored. hr.ge also
     only opens detail pages for new announcements. If jobs.ge answers 403/410/429, the run stops
     requesting it; listings already seen keep their stored copy.
2. Upserts each job by `(platform, external_job_id)`, sets `is_active=True` and `last_seen_at=now`.
3. For each source that returned data, jobs missing from today's feed are marked `is_active=False`
   (hidden from the API). If a source fails or returns nothing, its jobs are left untouched.
4. Fetched jobs not seen for **7 days** (`STALE_JOB_GRACE_DAYS`) are deleted.
5. Exits with a non-zero code if no jobs were fetched at all, so the run shows as failed in Railway.
6. `enrich_jobs_ai` then sends active fetched jobs (newest first) to AI for a short summary,
   concise responsibilities and qualifications, and the required / preferred skills and tools.
   Each skill must be quoted from the posting, so tools from the company blurb are not stored.
   The result is kept until the title or description changes, so each posting is summarized once;
   `fetch_jobs` does not overwrite it. Jobs not summarized yet show the rule-based fields.
   - Providers: Groq's free models first, each paced to its 8K tokens/minute limit and set aside when it
     reaches its 200K tokens/day limit; then Gemini. A job is ~2.7K tokens, so Groq's free tier covers
     ~220 jobs a day and Gemini the rest. When both are used up the run stops and the remaining jobs
     are summarized on the next runs (the first backlog of several thousand jobs takes several days).
   - The run also stops after 10 failed calls in a row (bad key, removed model). `--force` regenerates everything.

---

## 4. Checking that it runs

- Railway: Cron service → **Deployments** shows one run per day with logs.
- Data: `GET /api/search?sort=newest` — `fetched_at` of fetched jobs should be from the last 24 h.
- Manual run (e.g. Railway shell): `python manage.py fetch_jobs`
