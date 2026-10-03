# Railway: Daily cron for job data updates (`fetch_jobs`)

Fetched jobs (jobs.ge, Greenhouse, Lever, Ashby, Remotive) are refreshed **once a day** by a
**separate Railway Cron service**. Employer-posted jobs (`platform="employer"`) are created
instantly through the API and are never modified or deleted by `fetch_jobs`.

There is no HTTP trigger endpoint; the cron service runs the management command directly.

---

## 1. Web service (no change)

Keep the existing Django service as is (start command from `railway.toml` / `Procfile`).
Do **not** use the cron command as the web service start command.

---

## 2. Cron service for `fetch_jobs`

1. In the Railway project, click **New** → **Empty Service** (or duplicate the web service).
2. Connect it to the **same GitHub repo** (Breneo-job-aggregator), same branch.
3. **Settings** for this service:
   - **Config-as-code path:** `railway.cron.toml` (otherwise `railway.toml` forces the Gunicorn start
     command and the cron run never exits). That file already sets the values below.
   - **Custom Start Command:**
     ```bash
     python manage.py migrate --noinput && python manage.py fetch_jobs
     ```
   - **Cron Schedule:** `0 20 * * *` — every day at 20:00 UTC = **00:00 Georgia time (UTC+4)**.
   - **Restart Policy:** `Never` (a cron run must exit; it must not be restarted in a loop).
4. **Variables:** reference the same variables as the web service — at minimum `DATABASE_URL`
   (link the Postgres service). Add any keys the fetchers use (e.g. `GEMINI_API_KEY` if set on web).
5. Deploy. Then open the service → **Deployments** and check the logs of the next run.

If a run is still active when the next one is due, Railway skips the new run.

---

## 3. What a run does

1. Fetches every source in `COMPANIES` (`jobs/management/commands/fetch_jobs.py`).
2. Upserts each job by `(platform, external_job_id)`, sets `is_active=True` and `last_seen_at=now`.
3. For each source that returned data, jobs missing from today's feed are marked `is_active=False`
   (hidden from the API). If a source fails or returns nothing, its jobs are left untouched.
4. Fetched jobs not seen for **7 days** (`STALE_JOB_GRACE_DAYS`) are deleted.
5. Exits with a non-zero code if no jobs were fetched at all, so the run shows as failed in Railway.

---

## 4. Checking that it runs

- Railway: Cron service → **Deployments** shows one run per day with logs.
- Data: `GET /api/search?sort=newest` — `fetched_at` of fetched jobs should be from the last 24 h.
- Manual run (e.g. Railway shell): `python manage.py fetch_jobs`
