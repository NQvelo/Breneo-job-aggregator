# How to Fetch Jobs: Local vs Render.com

## Quick Answer

**Run `fetch_jobs` on Render.com** to populate your production PostgreSQL database. This is where your API is running.

## Option 1: Run on Render.com (Production) ✅ Recommended

This populates your **production database** that your API uses.

### Method A: Using Render Shell (Easiest)

1. **Go to Render Dashboard**:

   - Open https://dashboard.render.com/
   - Click on your **web service** (not cron job)

2. **Open Shell**:

   - Click on **"Shell"** tab (at the top, next to Logs)
   - Or click **"SSH"** button (if available)

3. **Run the command**:

   ```bash
   python manage.py fetch_jobs
   ```

4. **Wait for completion**:

   - You'll see output like:
     ```
     Fetching jobs for Intercom (greenhouse)...
       ✓ Fetched 202 jobs for Intercom
     Fetching jobs for Figma (greenhouse)...
       ✓ Fetched 170 jobs for Figma
     ...
     ✓ Successfully fetched/updated 3829 jobs
     📊 Active jobs in database: 3829
     ```

5. **Done!** Your API should now have jobs.

### Method B: Using Trigger Endpoint (Alternative)

If you have the trigger endpoint set up:

1. **Get your secret** (if you set `FETCH_SECRET`):

   - Go to your web service → Environment
   - Copy `FETCH_SECRET` value

2. **Call the endpoint**:

   ```bash
   curl https://your-app.onrender.com/api/trigger-fetch?secret=YOUR_SECRET
   ```

   Or without secret:

   ```bash
   curl https://your-app.onrender.com/api/trigger-fetch
   ```

3. **Check the response** - should show success

### Method C: Via Cron Job (If Already Configured)

If you already set up a cron job:

1. **Wait for it to run** (if scheduled)
2. **Or trigger manually**:
   - Go to your cron job service
   - Click "Manual Deploy" or "Trigger Now" (if available)

## Option 2: Run Locally (Development Only)

**Only use this if** you're testing locally with a local database (SQLite).

### Step 1: Check Your Local Database

1. **Make sure you're in the project directory**:

   ```bash
   cd /Users/macbookpro/job-aggregator
   ```

2. **Activate virtual environment** (if using one):

   ```bash
   source venv/bin/activate
   ```

3. **Make sure DATABASE_URL is NOT set** (to use local SQLite):

   ```bash
   unset DATABASE_URL
   ```

4. **Check local database**:
   ```bash
   python check_database.py
   ```

### Step 2: Run Fetch Locally

```bash
python manage.py fetch_jobs
```

**Note**: This only updates your **local SQLite database**, not your production PostgreSQL database on Render!

## Which Should You Use?

### ✅ Use Render.com (Production)

**Use this if**:

- Your API is running on Render
- You want jobs to appear in your production API
- You migrated to PostgreSQL on Render

**How**: Use Method A (Render Shell) above

### ❌ Don't Use Local

**Don't use local if**:

- Your production database is on Render
- Your API is on Render
- You're trying to fix the empty API issue

**Why**: Local runs against your local SQLite file, not your production PostgreSQL database.

## Step-by-Step Guide for Render.com

### Step 1: Access Render Shell

1. Go to https://dashboard.render.com/
2. Click on your **web service** name
3. Click **"Shell"** tab at the top
4. A terminal window will open

### Step 2: Run Fetch Command

In the Render shell, type:

```bash
python manage.py fetch_jobs
```

Press Enter.

### Step 3: Monitor Output

You'll see:

```
Starting job fetch...
Fetching jobs for Intercom (greenhouse)...
  ✓ Fetched 202 jobs for Intercom
Fetching jobs for Figma (greenhouse)...
  ✓ Fetched 170 jobs for Figma
...
✓ Successfully fetched/updated 3829 jobs
📊 Active jobs in database: 3829
```

**Note**: This may take 2-5 minutes depending on how many companies you're fetching from.

### Step 4: Verify

After it completes:

1. **Check API**:

   ```bash
   curl https://your-app.onrender.com/api/search
   ```

   Should return jobs, not empty array `[]`

2. **Or visit in browser**:
   ```
   https://your-app.onrender.com/api/search
   ```

## Troubleshooting

### Error: "Command not found: python"

**Fix**: Try `python3` instead:

```bash
python3 manage.py fetch_jobs
```

### Error: "No module named 'django'"

**Fix**: You might be in the wrong directory. Check:

```bash
pwd
ls manage.py
```

Should show the project root.

### Error: "Database connection failed"

**Fix**: Verify `DATABASE_URL` is set:

```bash
echo $DATABASE_URL
```

Should show your PostgreSQL connection string. If empty, go to Environment tab and set it.

### No Output / Command Hangs

**Fix**: This is normal - fetching jobs takes time. Wait 2-5 minutes.

### Jobs Still Not Appearing

**Fix**:

1. Check database status: `python check_database.py`
2. Verify migrations ran: `python manage.py showmigrations`
3. Check logs for errors

## After First Fetch

Once jobs are fetched:

1. **Set up cron job** (if not already done):

   - Go to Render → New → Cron Job
   - Command: `python manage.py fetch_jobs`
   - Schedule: `0 2 * * *` (daily at 2 AM)

2. **Jobs will auto-update** daily via cron

## Summary

- **To populate production database**: Run on Render.com (Shell)
- **Command**: `python manage.py fetch_jobs`
- **Where**: Render Dashboard → Your Web Service → Shell tab
- **Time**: 2-5 minutes
- **Result**: Jobs appear in your API

## Visual Guide

```
Render Dashboard
  └─ Your Web Service
      └─ Shell Tab  ← Click here
          └─ Terminal opens
              └─ Type: python manage.py fetch_jobs
                  └─ Wait for completion
                      └─ Check API: /api/search
```

That's it! Once you run `fetch_jobs` on Render, your API will have data.
