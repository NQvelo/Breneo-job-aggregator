## Using PostgreSQL on Railway with `job-aggregator`

This guide explains how to connect your Django project (`job-aggregator`) to a PostgreSQL database on Railway.

Your `settings.py` is already set up to use a `DATABASE_URL` environment variable, so the main work is creating the database on Railway and wiring up environment variables.

---

## 1. Prerequisites

- **Deployed app on Railway** pointing to this repo.
- **Django** and **`dj-database-url`** installed in your project.
  - If not sure, add `dj-database-url` to your dependencies (e.g. `requirements.txt`), redeploy, and continue.

---

## 2. Create a PostgreSQL database on Railway

1. Log in to Railway and open your project that runs this Django app.
2. Click **Add** → **Database** → **PostgreSQL**.
3. Wait for Railway to provision the database (status becomes “Running”).

Railway will generate connection information and usually set a `DATABASE_URL` variable automatically for that database.

---

## 3. Link the database to your Django service (UI)

1. In Railway, go to your **Django service** (the one running this repo).
2. Open the **Variables / Environment** tab.
3. Click **Link** (or “New Variable from Service”) and select your **PostgreSQL database**.
4. Confirm that an environment variable named **`DATABASE_URL`** is present on your Django service.
   - It should look something like:

   ```text
   postgres://USER:PASSWORD@HOST:PORT/DB_NAME
   ```

---

## 3.1 Link using the Postgres service variable (`${{ Postgres.DATABASE_URL }}`)

Railway also shows a “Connect to Postgres” snippet for your database. To follow that:

1. In the **database service** page, copy the value it shows:

   ```text
   ${{ Postgres.DATABASE_URL }}
   ```

2. Go back to your **Django service → Variables**.
3. Create a **new variable** named:

   ```text
   DATABASE_URL
   ```

4. Paste the value:

   ```text
   ${{ Postgres.DATABASE_URL }}
   ```

This tells Railway to inject your Postgres connection string into the `DATABASE_URL` environment variable that Django is already using.

> **Why this works:**  
> In `job_aggregator/settings.py`, if `DATABASE_URL` is present, Django uses it for the default database via `dj_database_url.parse(...)`. If `DATABASE_URL` is missing, the app falls back to SQLite.

---

## 4. Configure other important environment variables

In the same **Variables** tab for your Django service, ensure these are set:

- **`DJANGO_SECRET_KEY`**: a long random string (keep this secret).
- **`DJANGO_DEBUG`**: set to `False` for production.
- **`ALLOWED_HOSTS`** (optional): if you want to override the defaults in `settings.py`, set to a comma‑separated list or `*` for “allow all” (not recommended for production).

Example:

```text
DJANGO_SECRET_KEY=change-me-to-a-long-random-string
DJANGO_DEBUG=False
ALLOWED_HOSTS=your-app-name.up.railway.app
```

> Note: `settings.py` already includes `.railway.app` in `ALLOWED_HOSTS` by default, so you usually don’t need to change this unless you want more control.

---

## 5. Run database migrations on Railway

After `DATABASE_URL` is configured and your service has been redeployed with it:

1. Open your Railway project.
2. For your Django service, open the **Shell** / **Console** (or run a one‑off command).
3. Run:

```bash
python manage.py migrate
```

4. (Optional) Create a superuser for the Django admin:

```bash
python manage.py createsuperuser
```

This will create all tables in your new PostgreSQL database.

---

## 5.1 Run migrations using the Railway CLI (`railway shell`)

You can also run Django commands from your local terminal using the Railway CLI ([docs](https://docs.railway.com/cli)):

1. **Install the CLI** (one option for macOS):

   ```bash
   brew install railway
   ```

   Or via npm (any OS with Node 16+):

   ```bash
   npm i -g @railway/cli
   ```

2. **Log in and link your project**:

   ```bash
   railway login
   railway link
   ```

3. **Open a shell inside your Django service with all env vars (including `DATABASE_URL`)**:

   ```bash
   railway shell
   ```

4. Inside that shell, run your Django commands:

   ```bash
   python manage.py migrate
   python manage.py createsuperuser  # optional
   ```

The CLI way does the same thing as the web console, but can be more convenient if you prefer the terminal.

---

## 6. Verify the connection

1. Open your deployed Railway URL (e.g. `https://your-app-name.up.railway.app`).
2. Hit an endpoint that touches the database (or open Django admin if enabled).
3. If everything is wired correctly, requests should succeed without database errors.

If you see errors like “could not connect to server” or “no such table”, check:

- `DATABASE_URL` is set on the **Django service**, not only on the database service.
- You redeployed after setting variables.
- `python manage.py migrate` completed successfully in Railway.

---

## 7. Local development with PostgreSQL (optional)

You can keep using SQLite locally, or switch to PostgreSQL:

- **Keep SQLite locally**: do nothing. With no `DATABASE_URL` defined, `settings.py` uses SQLite automatically.
- **Use PostgreSQL locally**:
  1. Install PostgreSQL on your machine or run it via Docker.
  2. Create a local database.
  3. Set a `DATABASE_URL` in your local environment, for example:

     ```text
     export DATABASE_URL=postgres://USER:PASSWORD@localhost:5432/your_local_db
     ```

  4. Run:

     ```bash
     python manage.py migrate
     ```

---

## 8. Summary

- **Railway PostgreSQL** provides a `DATABASE_URL` connection string.
- Your Django project is already configured to use **`DATABASE_URL`** for PostgreSQL when present, and **SQLite** otherwise.
- Setting `DATABASE_URL` on the Django service + running `python manage.py migrate` is the key step to fully switch to PostgreSQL on Railway.

---

## 9. Troubleshooting

### `ModuleNotFoundError: No module named 'breneo'`

The Django project module is **`job_aggregator`**, not `breneo`. If the start command on Railway is set to something like `gunicorn breneo.wsgi`, change it:

1. Open your **web service** in Railway → **Settings** (or **Deploy**).
2. Set **Start Command** to:
   ```bash
   gunicorn job_aggregator.wsgi --bind 0.0.0.0:$PORT --log-file -
   ```
   Or leave it **empty** so Railway uses the **Procfile** (`web: gunicorn job_aggregator.wsgi --log-file -`). If you use the Procfile, ensure the service is set to use the `web` process.

The repo includes a **`railway.toml`** that sets the correct start command (and a longer timeout, single worker) so the dashboard does not need a custom start command.

### Worker timeout / "Perhaps out of memory?"

If workers are killed with `WORKER TIMEOUT` or "Perhaps out of memory?" every ~30 seconds:

- **Use the repo’s start command** so the 120s timeout and 1 worker are applied: either leave **Start Command** empty in Railway (so the **Procfile** is used) or set it to:
  ```bash
  gunicorn job_aggregator.wsgi --bind 0.0.0.0:$PORT --log-file - --timeout 120 --workers 1
  ```
  The **Procfile** and **railway.toml** in this repo already include `--timeout 120 --workers 1`; a custom start command in the Railway dashboard **overrides** them, so if you set one, it must include `--timeout 120`.
- Increase the service **memory** in Railway if the plan allows it.
- Ensure the **database is running** before the web service; "database container is starting up" can make the app hang during startup and hit the timeout.

