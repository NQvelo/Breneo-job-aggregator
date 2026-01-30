# Fix: Empty Database After PostgreSQL Migration

## Issue: API Returns `[]` (Empty Array)

After migrating to PostgreSQL, your database is likely **empty** because:

1. ✅ Migrations created the tables
2. ❌ But **no data was migrated** from SQLite to PostgreSQL
3. ❌ Jobs haven't been fetched yet

## Quick Fix

### Step 1: Check Database Status

Run the diagnostic script:

```bash
python check_database.py
```

This will show:
- Database connection status
- Number of companies
- Number of jobs (total, active, inactive)

### Step 2: Fetch Jobs

If the database is empty, fetch jobs:

```bash
python manage.py fetch_jobs
```

This will:
- Fetch jobs from all configured companies
- Save them to PostgreSQL
- Mark them as active

### Step 3: Verify

After fetching, check again:

```bash
python check_database.py
```

Or check the API:
```bash
curl https://your-app.onrender.com/api/search
```

## Common Issues

### Issue 1: Database is Empty

**Symptom**: `check_database.py` shows `Total: 0`

**Fix**: Run `python manage.py fetch_jobs`

### Issue 2: All Jobs Are Inactive

**Symptom**: `Total: 1000` but `Active: 0`

**Fix**: Run `python manage.py fetch_jobs` (this will fetch new jobs and mark them active)

### Issue 3: Database Connection Error

**Symptom**: `check_database.py` shows connection error

**Fix**: 
1. Verify `DATABASE_URL` environment variable is set
2. Check PostgreSQL is running in Render dashboard
3. Verify connection string is correct

### Issue 4: Migrations Not Run

**Symptom**: `check_database.py` shows "relation does not exist"

**Fix**: Run migrations:
```bash
python manage.py migrate
```

## Step-by-Step Fix for Empty Database

### On Render.com (Production) ✅ **Use This**

**Important**: Run `fetch_jobs` on Render.com to populate your production database!

1. **Go to Render Dashboard**: https://dashboard.render.com/
2. **Click on your web service** (not the cron job)
3. **Click "Shell" tab** (at the top, next to Logs)
4. **In the terminal that opens, run**:
   ```bash
   python manage.py fetch_jobs
   ```
5. **Wait for completion** (2-5 minutes)
6. **Check your API** - jobs should now appear!

**See `HOW_TO_FETCH_JOBS.md` for detailed visual guide**

### Local (Development Only - Not Recommended for Production)

**Note**: Only use this if testing locally with SQLite. This won't update your production database on Render!

1. **Go to Render Shell**:
   - Open your web service in Render dashboard
   - Click "Shell" tab (or SSH)

2. **Run diagnostic**:
   ```bash
   python check_database.py
   ```

3. **If empty, fetch jobs**:
   ```bash
   python manage.py fetch_jobs
   ```

4. **Verify**:
   ```bash
   python check_database.py
   ```

### Locally (Development)

1. **Set DATABASE_URL** (if testing PostgreSQL locally):
   ```bash
   export DATABASE_URL="postgresql://..."
   ```

2. **Or use SQLite** (default, no DATABASE_URL needed):
   ```bash
   unset DATABASE_URL
   python manage.py migrate
   python manage.py fetch_jobs
   ```

## After Migration Checklist

- [ ] Migrations ran successfully (`python manage.py migrate`)
- [ ] Database has companies (`python check_database.py`)
- [ ] Database has active jobs (`python check_database.py`)
- [ ] API returns jobs (`GET /api/search`)
- [ ] Cron job is configured to fetch jobs automatically

## Why This Happens

PostgreSQL migration **only creates tables** - it doesn't migrate data:

1. SQLite data stays in `db.sqlite3` (local file)
2. PostgreSQL starts with empty tables
3. You need to **fetch jobs again** to populate PostgreSQL

This is normal and expected. Just run `fetch_jobs` after migration.

## Automated Solution

Set up your cron job to run automatically:

1. Go to Render dashboard → Cron Job
2. Configure to run `python manage.py fetch_jobs`
3. Schedule: `0 2 * * *` (daily at 2 AM)

This will automatically populate your database daily.

## Verify Everything Works

After fetching jobs, test:

1. **API Endpoint** (`/api/`):
   ```bash
   curl https://your-app.onrender.com/api/
   ```
   Should return companies with jobs (not empty array)

2. **Search Endpoint** (`/api/search`):
   ```bash
   curl https://your-app.onrender.com/api/search
   ```
   Should return paginated jobs

3. **Check Database**:
   ```bash
   python check_database.py
   ```
   Should show active jobs > 0

## Still Not Working?

1. **Check Logs**: Look for errors in Render dashboard → Logs
2. **Verify Environment**: Check `DATABASE_URL` is set correctly
3. **Test Connection**: Run `python check_database.py` to see connection status
4. **Check Migrations**: Verify all migrations ran (`python manage.py showmigrations`)
