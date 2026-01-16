# ⚠️ SQLite Limitation on Render.com

## Critical Issue

**SQLite databases on Render.com are EPHEMERAL** - they get wiped on every deployment or restart.

This means:
- ✅ Jobs are being fetched and saved successfully
- ❌ The database gets wiped on the next deploy/restart
- ❌ Your jobs disappear after each deployment

## Why This Happens

Render.com uses ephemeral filesystems for free-tier services:
- Files are lost on every deploy
- The database file (`db.sqlite3`) is recreated each time
- Cron job and web service might use different database instances

## The Real Problem

Your `fetch_jobs` command is working correctly:
- It's fetching 3829 jobs
- Jobs are being saved to the database
- **BUT** the database gets wiped on the next restart/deploy

This is why you see "Total jobs fetched/updated: 3829" but they're not in the database when you check.

## Solution: Use PostgreSQL

To persist data permanently on Render.com, you must use **PostgreSQL**:

### Step 1: Create PostgreSQL Database on Render

1. Go to Render dashboard
2. Click "New +" → "PostgreSQL"
3. Configure:
   - **Name**: `job-aggregator-db`
   - **Database**: `jobaggregator`
   - **User**: (auto-generated)
   - **Region**: Same as your web service
4. Copy the **Internal Database URL** (starts with `postgresql://`)

### Step 2: Update Settings

Add to `job_aggregator/settings.py`:

```python
import dj_database_url

# Database
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///db.sqlite3',
        conn_max_age=600
    )
}
```

Or for Render specifically:

```python
import dj_database_url
import os

# Database
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Render PostgreSQL
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    # Local SQLite fallback
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
```

### Step 3: Install Required Package

Add to `requirements.txt`:

```
dj-database-url>=2.1.0
psycopg2-binary>=2.9.9
```

### Step 4: Set Environment Variable

In Render dashboard, add to both **web service** and **cron job**:

- **Key**: `DATABASE_URL`
- **Value**: Your PostgreSQL connection string (from Step 1)

**Important**: Set this in BOTH services (web + cron) so they use the same database.

### Step 5: Run Migrations

After setting up PostgreSQL:

1. Push your changes to Git
2. Render will automatically rebuild
3. The build will run migrations automatically
4. Or manually run: `python manage.py migrate`

## Alternative: Keep Using SQLite (Temporary Solution)

If you want to keep using SQLite for now (data will still be lost on deploy):

1. ✅ The `fetch_jobs` command is already fixed with batch commits
2. ✅ Jobs will be saved temporarily
3. ❌ They'll be lost on next deploy/restart

**Use this only for testing** - not recommended for production.

## Verify Database is Working

After setting up PostgreSQL, check:

1. **Cron job logs**: Should show "Active jobs in database: X" after fetch
2. **API**: `/api/search` should show jobs
3. **Admin panel**: Jobs should appear in Django admin

## Migration Checklist

- [ ] Create PostgreSQL database on Render
- [ ] Add `dj-database-url` and `psycopg2-binary` to `requirements.txt`
- [ ] Update `settings.py` with `DATABASE_URL` support
- [ ] Set `DATABASE_URL` environment variable in web service
- [ ] Set `DATABASE_URL` environment variable in cron job
- [ ] Deploy and verify migrations ran
- [ ] Test `fetch_jobs` command
- [ ] Verify jobs appear in database

## Need Help?

1. Check Render dashboard → PostgreSQL → "Connections" tab
2. Verify environment variables are set correctly
3. Check build logs for migration errors
4. Test database connection manually in shell
