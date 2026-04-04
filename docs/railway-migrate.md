# Run Django migrations on Railway

## Option A — Railway dashboard (no laptop DNS issues)

1. Open [Railway](https://railway.app) → your project → the **web** service (the one running Django).
2. Open the **Shell** tab (or **Deployments** → active deployment → **Shell**).
3. Run:

```bash
python manage.py migrate --noinput
```

4. Confirm output includes `Applying jobs.…` with no errors.

The app runs **inside** Railway’s network, so `DATABASE_URL` with `*.railway.internal` resolves correctly.

---

## Option B — Railway CLI on your computer

1. Install the [Railway CLI](https://docs.railway.com/develop/cli) and log in:

```bash
railway login
```

2. From your project root, link the service:

```bash
railway link
```

Choose the project, environment, and **Django web** service.

3. Start a subshell with that service’s variables:

```bash
railway shell
```

4. Use the same Python as production if you can (optional). Then migrate:

```bash
python manage.py migrate --noinput
```

**Private Postgres URL on your laptop:** `DATABASE_URL` often uses `postgres.railway.internal`, which **does not resolve** on your Mac. `job_aggregator/settings.py` runs a quick DNS check: if that host does not resolve and **`DATABASE_PUBLIC_URL`** is set, Django uses the public URL automatically.

**You must expose the public URL on the web service:** Railway puts `DATABASE_PUBLIC_URL` on the **Postgres** service by default. On the **web** service, add a variable reference: **Variables → New Variable → Reference** → choose Postgres → `DATABASE_PUBLIC_URL` (keep the name `DATABASE_PUBLIC_URL`).

If it is missing, Django raises `ImproperlyConfigured` with the same instructions instead of a long psycopg2 traceback.

**Manual override** (e.g. one-off in `railway shell` after copying the value from Postgres → Variables):

```bash
export DATABASE_URL="$DATABASE_PUBLIC_URL"
python manage.py migrate --noinput
```

---

## Automatic migrations on each deploy

`railway.toml` runs `migrate` in two places:

1. **`releaseCommand`** — ideal, runs before the new deployment goes live.
2. **`startCommand`** — runs `migrate` immediately before Gunicorn starts, so the DB stays in sync even if Railway never runs the release phase (common when the dashboard overrides the start command or ignores config-as-code).

After pushing this config, **redeploy** once; check runtime logs for `Applying jobs.0022…` / `0023…`.

If the dashboard **Custom Start Command** overrides `railway.toml`, paste the same pattern:

`sh -c 'python manage.py migrate --noinput && exec gunicorn …'`

---

## Check applied migrations

In Railway **Shell** (dashboard or after `railway shell`):

```bash
python manage.py showmigrations jobs
```

Lines marked `[X]` are applied on that database.
