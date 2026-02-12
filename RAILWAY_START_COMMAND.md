# Railway start command (fix worker timeout)

If your web service shows **WORKER TIMEOUT** or **Perhaps out of memory?** in the logs, Railway is likely **not** using the start command from the Procfile or `railway.toml` (e.g. a custom Start Command in the dashboard overrides it).

## Fix: set the start command in Railway

1. In [Railway](https://railway.app), open your **project** → **web service** (the one that runs the Django app).
2. Go to **Settings** (or **Variables** tab and find **Deploy** section).
3. Find **Start Command** / **Custom Start Command**.
4. Either:
   - **Clear it** so Railway uses the **Procfile** (recommended), or
   - Set it to this **exact** string (copy-paste):

```bash
gunicorn job_aggregator.wsgi --bind 0.0.0.0:$PORT --log-file - --timeout 300 --workers 1 --preload
```

5. **Redeploy** the service (e.g. **Deploy** → **Redeploy** or push a new commit).

## What this does

| Option        | Purpose |
|--------------|--------|
| `--timeout 300` | Worker is allowed 5 minutes to handle a request (avoids WORKER TIMEOUT). |
| `--workers 1`   | One worker to reduce memory use. |
| `--preload`     | Load Django once in the master before forking; first request is then fast. |
| `--bind 0.0.0.0:$PORT` | Listen on Railway’s port. |

## Health check

In the same service, set **Health Check Path** (if available) to **`/health/`** so the first request is lightweight and returns quickly.

## After changing

Redeploy and check logs. You should no longer see workers killed every 30–120 seconds. If timeouts continue, increase memory for the service in Railway or open an issue with the latest logs.
