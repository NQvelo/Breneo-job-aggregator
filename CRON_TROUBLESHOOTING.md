# Cron Job Troubleshooting Guide

## ⚠️ CRITICAL: SQLite Database Issue

**If jobs are being fetched but not appearing in the database**, this is likely because:

1. **Render.com uses ephemeral filesystems** - SQLite databases get wiped on every deploy/restart
2. **Jobs are saved** but disappear after the next restart
3. **Solution**: You need to use **PostgreSQL** instead of SQLite (see `SQLITE_RENDER_WARNING.md`)

The `fetch_jobs` command is working correctly - the issue is that SQLite doesn't persist on Render.com.

---

## Issue: Cron Job Not Fetching New Jobs

If your Render.com cron job is not fetching new jobs automatically, follow these troubleshooting steps:

### Step 1: Check Cron Job Configuration

In Render dashboard, verify your cron job is configured correctly:

**Correct Settings**:

- **Command**: `python manage.py fetch_jobs`
- **Schedule**: `0 2 * * *` (or your preferred schedule)
- **Build Command**: `pip install -r requirements.txt && python manage.py migrate`
- **Working Directory**: Leave empty or set to `/` (root)
- **Branch**: Your main branch (usually `main` or `master`)

**Important**: The command should be `python manage.py fetch_jobs` NOT `./manage.py fetch_jobs`

### Step 2: Verify Environment Variables

Make sure your cron job has the same environment variables as your web service:

Required:

- `DJANGO_SECRET_KEY` - Must match your web service
- `DJANGO_DEBUG` - Should be `False` in production
- Any other env vars your app needs

**To check**: Go to your cron job → Environment → Compare with web service

### Step 3: Check Logs

1. Go to Render dashboard
2. Click on your cron job service
3. Click "Logs" tab
4. Look for:
   - "Starting job fetch..." - Command started
   - "Fetching jobs for X..." - Processing companies
   - "✓ Successfully fetched/updated X jobs" - Success
   - Any error messages

**Common log messages**:

- ✅ "Starting job fetch..." - Command is running
- ✅ "✓ Fetched X jobs for CompanyName" - Jobs are being fetched
- ❌ "Database connection failed" - Environment issue
- ❌ "No fetcher for platform: X" - Missing fetcher
- ❌ "Error fetching jobs for X" - API/network issue

### Step 4: Test Manually

Test the command manually using Render's shell:

1. Go to your Render dashboard
2. Click on your cron job service
3. Click "Shell" (or SSH into the instance)
4. Run: `python manage.py fetch_jobs`

If it works in shell but not in cron, it's likely a cron configuration issue.

### Step 5: Verify Database Access

The cron job needs access to the same database as your web service:

**For SQLite** (current setup):

- The cron job runs on the same instance as the web service
- Database file location: `/opt/render/project/src/db.sqlite3`
- Should work automatically

**For PostgreSQL** (if you migrate later):

- Use Render's managed PostgreSQL
- Set `DATABASE_URL` environment variable
- Cron job will automatically connect

### Step 6: Check Command Format

Make sure your cron job command is exactly:

```
python manage.py fetch_jobs
```

**Common mistakes**:

- ❌ `./manage.py fetch_jobs` - Won't work
- ❌ `python3 manage.py fetch_jobs` - Should be `python`
- ❌ `cd /path && python manage.py fetch_jobs` - Not needed, already in project root

### Step 7: Verify Schedule

Check your cron schedule format:

- `0 2 * * *` - Daily at 2:00 AM UTC
- `0 */6 * * *` - Every 6 hours
- `0 */12 * * *` - Every 12 hours

**To test immediately**: Temporarily change schedule to `*/5 * * * *` (every 5 minutes) and check if it runs.

### Step 8: Check for Errors

Common issues:

1. **Silent failures**: Check if command is actually running

   - Look for "Starting job fetch..." in logs
   - If not present, command isn't executing

2. **Database locked**: Multiple processes accessing SQLite

   - Shouldn't happen if cron runs when web service is idle
   - Consider using PostgreSQL for production

3. **Missing dependencies**: Some packages not installed

   - Check build logs for installation errors
   - Verify `requirements.txt` is up to date

4. **Network timeouts**: API calls failing
   - Check for "Error fetching" messages in logs
   - Some companies' APIs might be slow/down

### Step 9: Verify Jobs Are Being Saved

After cron runs, check if jobs were actually saved:

1. Check API: `GET /api/search?recent=true&sort=recently_fetched`
2. Check database directly (if you have access)
3. Check admin panel: `GET /admin/jobs/job/`

### Step 10: Test with Trigger Endpoint

Test if the command works when called via API:

```bash
# Call the trigger endpoint
curl https://your-app.onrender.com/api/trigger-fetch?secret=YOUR_SECRET

# Check response
# Should return: {"status": "success", "message": "Job fetching completed", ...}
```

If this works but cron doesn't, it's a cron configuration issue.

## Quick Fixes

### Fix 1: Verify Command Format

```
Command: python manage.py fetch_jobs
```

### Fix 2: Add Build Command

```
Build Command: pip install -r requirements.txt && python manage.py migrate
```

### Fix 3: Check Environment Variables

Ensure `DJANGO_SECRET_KEY` is set in cron job environment.

### Fix 4: Use Trigger Endpoint Instead

If cron keeps failing, use external cron service:

- Set up cron-job.org to call `/api/trigger-fetch`
- More reliable than Render cron jobs

## Still Not Working?

1. **Check Render Status**: Render might have service issues
2. **Verify Billing**: Free tier has limitations
3. **Contact Support**: Render has good support for debugging cron jobs
4. **Check for Rate Limits**: Some company APIs might rate limit requests

## Expected Behavior

When working correctly, you should see in logs:

```
Starting job fetch...
Fetching jobs for Intercom (greenhouse)...
  ✓ Fetched 15 jobs for Intercom
Fetching jobs for Figma (greenhouse)...
  ✓ Fetched 23 jobs for Figma
...
✓ Successfully fetched/updated 150 jobs
```

Then new jobs appear in `/api/search?recent=true` within minutes.
