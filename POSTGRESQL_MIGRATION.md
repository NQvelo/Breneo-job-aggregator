# PostgreSQL Migration Guide for Render.com

This guide will help you migrate from SQLite to PostgreSQL on Render.com to ensure your data persists across deployments.

## Step 1: Create PostgreSQL Database on Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"PostgreSQL"**
3. Configure the database:

   - **Name**: `job-aggregator-db` (or any name you prefer)
   - **Database**: `jobaggregator` (or leave default)
   - **User**: Auto-generated (you can customize)
   - **Region**: **Same region as your web service** (important for performance)
   - **PostgreSQL Version**: Latest (14 or 15 recommended)
   - **Plan**: Start with Free tier (upgrade later if needed)

4. Click **"Create Database"**
5. Wait for database to be provisioned (usually 1-2 minutes)

## Step 2: Get Database Connection String

After the database is created:

1. Click on your PostgreSQL database
2. Go to **"Info"** tab
3. Copy the **"Internal Database URL"** (looks like: `postgresql://user:password@host:5432/dbname`)

   **Important**: Use **Internal Database URL** (not External) for Render services in the same region.

4. Save this URL - you'll need it for environment variables

## Step 3: Add Required Packages

Update `requirements.txt` to include PostgreSQL support:

```bash
# Add these lines to requirements.txt
dj-database-url>=2.1.0
psycopg2-binary>=2.9.9
```

**Note**: `dj-database-url` automatically parses `DATABASE_URL` environment variable. `psycopg2-binary` is the PostgreSQL adapter for Python.

## Step 4: Update Django Settings

Update `job_aggregator/settings.py` to support both SQLite (local) and PostgreSQL (production):

```python
# At the top of settings.py, add:
import dj_database_url

# ... existing code ...

# ---------------------------
# DATABASE
# ---------------------------
# Use DATABASE_URL from environment if available (Render PostgreSQL)
# Otherwise, fall back to SQLite for local development
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Render PostgreSQL (production)
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    # SQLite (local development)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
```

This configuration:

- ✅ Uses PostgreSQL on Render (when `DATABASE_URL` is set)
- ✅ Uses SQLite locally (when `DATABASE_URL` is not set)
- ✅ Automatically handles connection pooling (`conn_max_age=600`)

## Step 5: Set Environment Variables on Render

Set `DATABASE_URL` in **BOTH** your web service and cron job:

### For Web Service:

1. Go to your **web service** in Render dashboard
2. Click **"Environment"** tab
3. Click **"Add Environment Variable"**
4. Add:
   - **Key**: `DATABASE_URL`
   - **Value**: Paste the **Internal Database URL** from Step 2
5. Click **"Save Changes"**

### For Cron Job:

1. Go to your **cron job service** in Render dashboard
2. Click **"Environment"** tab
3. Click **"Add Environment Variable"**
4. Add:
   - **Key**: `DATABASE_URL`
   - **Value**: Paste the **same Internal Database URL** from Step 2
5. Click **"Save Changes"**

**Important**: Both services must use the **same** `DATABASE_URL` so they share the same database.

## Step 6: Commit and Deploy

1. Commit your changes:

   ```bash
   git add requirements.txt job_aggregator/settings.py
   git commit -m "Migrate from SQLite to PostgreSQL"
   git push origin main
   ```

2. Render will automatically:
   - Install new packages (`dj-database-url`, `psycopg2-binary`)
   - Rebuild your services
   - Run migrations automatically (if configured in build command)

## Step 7: Run Migrations

After deployment, run migrations to create tables in PostgreSQL:

### Option A: Automatic (Recommended)

If your build command includes migrations:

```
pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput
```

Migrations will run automatically on deploy.

### Option B: Manual

If migrations don't run automatically:

1. Go to your web service in Render dashboard
2. Click **"Shell"** tab (or use SSH)
3. Run:
   ```bash
   python manage.py migrate
   ```

This will create all tables in PostgreSQL.

## Step 8: Verify Migration

### Check Database Connection:

1. Go to your web service logs
2. Look for successful startup (no database errors)

### Check if Data Exists:

1. Run your fetch command:

   ```bash
   python manage.py fetch_jobs
   ```

2. Check API:

   ```bash
   curl https://your-app.onrender.com/api/search
   ```

3. Verify jobs are being saved:
   - Check cron job logs for "Active jobs in database: X"
   - Jobs should persist across restarts

### Verify in PostgreSQL:

1. Go to your PostgreSQL database in Render
2. Click **"Connect"** → **"psql"** (if available)
3. Or use **"Data"** tab to view tables

## Step 9: Test Everything

1. **Test Web Service**:

   - Visit your API: `https://your-app.onrender.com/api/search`
   - Should return jobs (if any exist)

2. **Test Cron Job**:

   - Wait for cron to run (or trigger manually)
   - Check logs: Should show "Starting job fetch..." and "Active jobs in database: X"
   - Jobs should appear in API immediately

3. **Test Persistence**:
   - Fetch some jobs
   - Restart your web service
   - Jobs should still be in database (unlike SQLite)

## Troubleshooting

### Error: "No module named 'dj_database_url'"

**Fix**: Make sure `dj-database-url>=2.1.0` is in `requirements.txt` and you've pushed the changes.

### Error: "No module named 'psycopg2'"

**Fix**: Make sure `psycopg2-binary>=2.9.9` is in `requirements.txt`.

### Error: "Connection refused" or "Can't connect to database"

**Fix**:

- Verify `DATABASE_URL` is set correctly (use Internal Database URL)
- Check that web service and cron job are in the same region as database
- Verify database is active in Render dashboard

### Error: "relation does not exist"

**Fix**: Run migrations:

```bash
python manage.py migrate
```

### Jobs Still Not Persisting

**Fix**:

1. Verify `DATABASE_URL` is set in BOTH web service AND cron job
2. Check that migrations ran successfully
3. Verify both services are using the same database (check `DATABASE_URL` matches)
4. Check database logs in Render dashboard

### Local Development Still Using SQLite

This is **expected and correct**. Without `DATABASE_URL`, the settings fall back to SQLite for local development. This is fine for testing locally.

## Migration Checklist

- [ ] Created PostgreSQL database on Render
- [ ] Copied Internal Database URL
- [ ] Added `dj-database-url` and `psycopg2-binary` to `requirements.txt`
- [ ] Updated `settings.py` with PostgreSQL configuration
- [ ] Set `DATABASE_URL` in web service environment
- [ ] Set `DATABASE_URL` in cron job environment (same value)
- [ ] Committed and pushed changes
- [ ] Verified build succeeded on Render
- [ ] Ran migrations (`python manage.py migrate`)
- [ ] Tested fetching jobs
- [ ] Verified jobs persist after restart
- [ ] Checked API returns jobs correctly

## Next Steps

After successful migration:

1. **Monitor Database Usage**: Check PostgreSQL metrics in Render dashboard
2. **Set Up Backups**: Render PostgreSQL includes automatic backups (check backup settings)
3. **Optimize Performance**: Consider connection pooling if you have high traffic
4. **Upgrade Plan**: Free tier has limits - upgrade if needed

## Cost Notes

- **PostgreSQL Free Tier**: 1GB storage, 1GB RAM, 90 days retention
- **Upgrade**: $7/month for Starter plan (if needed)
- **Your SQLite was free but ephemeral** - PostgreSQL free tier is much better!

## Summary

After migration:

- ✅ Data persists across deployments
- ✅ Cron job and web service share same database
- ✅ Better performance with connection pooling
- ✅ Automatic backups included
- ✅ Can handle concurrent access (unlike SQLite)

Your `fetch_jobs` command will work exactly the same, but now jobs will persist!
