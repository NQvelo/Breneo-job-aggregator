# Railway: Cron for job data updates (`fetch_jobs`)

Use a **separate Cron service** so job data updates run on a schedule. Your **web service** keeps its normal start command.

---

## 1. Web service (no change)

Keep your existing Django service as is:

- **Start command:** `gunicorn job_aggregator.wsgi --log-file -`  
  (or leave blank if Railway uses the Procfile: `web: gunicorn job_aggregator.wsgi --log-file -`)

Do **not** use the cron command as the web service start command.

---

## 2. Add a Cron service for `fetch_jobs`

1. In your Railway project, click **Add Service** (or **New** → **Empty Service**).
2. Connect this service to the **same GitHub repo** (Breneo-job-aggregator).
3. **Settings** for this new service:
   - **Build:** Same as your Django service (same repo, Nixpacks will use `requirements.txt`).
   - **Start command:**  
     ```bash
     python manage.py fetch_jobs
     ```
   - **Cron Schedule:** Set a [crontab expression](https://docs.railway.com/guides/cron-jobs#crontab-expressions) (UTC). Examples:
     - Every 6 hours: `0 */6 * * *`
     - Every day at 00:00 UTC: `0 0 * * *`
     - Every day at 08:00 UTC: `0 8 * * *`
     - Minimum interval between runs: 5 minutes (e.g. every hour: `0 * * * *`).
4. **Variables:** Reuse the same env as your Django app (e.g. **Link** the Postgres service so this service gets `DATABASE_URL`). Add the same vars your Django service has if the command needs them (e.g. `DJANGO_SECRET_KEY` is not required for `fetch_jobs`; `DATABASE_URL` is).
5. Save. Railway will run `python manage.py fetch_jobs` on the schedule. The process must **exit** when done (this command does), so the next run can start on time.

---

## 3. Summary

| Service        | Start command                              | Cron schedule (example) |
|----------------|--------------------------------------------|--------------------------|
| Django (web)   | `gunicorn job_aggregator.wsgi --log-file -`| —                        |
| Cron (fetch)   | `python manage.py fetch_jobs`              | e.g. `0 */6 * * *` (every 6 h) |

Cron runs are in **UTC**. If a run is still “Active” when the next run is due, the new run is skipped until the previous one finishes.
