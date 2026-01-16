# Automated Job Fetching Setup

This document explains how to set up automatic job fetching without human interaction.

## Option 1: External Cron Service (Recommended - Easiest)

Use a free external cron service to call your API endpoint:

### Step 1: Set up Secret Token (Optional but Recommended)

Add to your Render environment variables:

- `FETCH_SECRET`: A secret token (e.g., generate a random string)

### Step 2: Configure Cron Service

Use services like:

- **cron-job.org** (free, easy to use)
- **EasyCron** (free tier available)
- **cronitor.io** (monitoring included)

Configure them to call:

```
https://your-app.onrender.com/api/trigger-fetch?secret=YOUR_SECRET_TOKEN
```

Or without secret (less secure):

```
https://your-app.onrender.com/api/trigger-fetch
```

### Recommended Schedule

- **Every 6 hours**: `0 */6 * * *`
- **Daily at 2 AM**: `0 2 * * *`
- **Every 12 hours**: `0 */12 * * *`
- **Every 4 hours**: `0 */4 * * *`

## Option 2: Render.com Cron Jobs

Render.com supports cron jobs:

1. Go to Render dashboard
2. Click "New +" → "Cron Job"
3. Configure:

   - **Name**: `job-aggregator-fetcher`
   - **Schedule**: `0 2 * * *` (daily at 2 AM UTC) - Cron format
   - **Command**: `python manage.py fetch_jobs`
   - **Environment**: Same as your web service
   - **Branch**: Your main branch
   - **Root Directory**: `/` (or leave default)

4. Set environment variables (same as web service):
   - `DJANGO_SECRET_KEY`
   - `DJANGO_DEBUG=False`
   - Any other required vars

## Option 2: Using APScheduler (In-App Scheduling)

If you want scheduling within your Django app, you can use APScheduler:

1. Install: `pip install apscheduler`
2. Add to `INSTALLED_APPS` in `settings.py`
3. Create a management command that runs on app startup

## Option 3: Background Worker Service

Set up a separate Render worker service that runs continuously:

1. Go to Render dashboard
2. Click "New +" → "Background Worker"
3. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python manage.py run_scheduler` (requires custom command)

## Option 4: External Cron Service

Use external services like:

- **Cron-job.org** - Free cron job service
- **EasyCron** - Cron job scheduling service
- **cronitor.io** - Cron job monitoring

Configure them to call a webhook endpoint that triggers job fetching.

## Current Implementation

The `fetch_jobs` management command:

- Fetches jobs from all configured companies
- Processes descriptions and extracts responsibilities, qualifications, team_description, and benefits
- Updates existing jobs and marks inactive ones
- Automatically formats bullet points

## Testing Locally

To test the automated fetching:

```bash
# Run once
python manage.py fetch_jobs

# Or set up a local cron (Linux/Mac)
# Add to crontab (crontab -e):
# 0 2 * * * cd /path/to/job-aggregator && /path/to/venv/bin/python manage.py fetch_jobs
```

## Monitoring

Check logs in Render dashboard:

- Web service logs show API requests
- Cron job/Worker logs show fetch_jobs execution
- Monitor for errors or failures

## Recommended Schedule

For job aggregators, recommended schedules:

- **Active job board**: Every 6 hours (`0 */6 * * *`)
- **Moderate activity**: Daily at 2 AM (`0 2 * * *`)
- **Low activity**: Every other day (`0 2 */2 * * *`)
