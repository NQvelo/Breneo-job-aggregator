#!/bin/bash
# Setup script for automated job fetching
# This script helps you set up automatic job fetching

echo "=== Automated Job Fetching Setup ==="
echo ""
echo "This script will help you set up automatic job fetching."
echo ""
echo "Options:"
echo "1. Render.com Cron Job (Recommended for Render deployment)"
echo "2. External Cron Service (cron-job.org, EasyCron, etc.)"
echo "3. Local Cron Setup (for local development)"
echo ""
read -p "Choose option (1-3): " option

case $option in
    1)
        echo ""
        echo "=== Render.com Cron Job Setup ==="
        echo ""
        echo "Follow these steps in Render dashboard:"
        echo "1. Go to your Render dashboard"
        echo "2. Click 'New +' → 'Cron Job'"
        echo "3. Configure:"
        echo "   - Name: job-aggregator-fetcher"
        echo "   - Schedule: 0 2 * * * (daily at 2 AM UTC)"
        echo "   - Command: python manage.py fetch_jobs"
        echo "   - Environment: Same as web service"
        echo ""
        echo "Recommended schedules:"
        echo "  - Every 6 hours: 0 */6 * * *"
        echo "  - Daily at 2 AM: 0 2 * * *"
        echo "  - Every 12 hours: 0 */12 * * *"
        ;;
    2)
        echo ""
        echo "=== External Cron Service Setup ==="
        echo ""
        echo "1. Set up FETCH_SECRET environment variable in Render"
        echo "   (Generate a random secret token)"
        echo ""
        echo "2. Use a cron service like cron-job.org:"
        echo "   URL: https://your-app.onrender.com/api/trigger-fetch?secret=YOUR_SECRET"
        echo "   Method: GET"
        echo "   Schedule: Choose your preferred schedule"
        echo ""
        echo "3. Test the endpoint:"
        echo "   curl https://your-app.onrender.com/api/trigger-fetch?secret=YOUR_SECRET"
        ;;
    3)
        echo ""
        echo "=== Local Cron Setup ==="
        echo ""
        VENV_PATH=$(which python | sed 's|/bin/python||')
        PROJECT_PATH=$(pwd)
        
        echo "Add this to your crontab (crontab -e):"
        echo ""
        echo "# Fetch jobs daily at 2 AM"
        echo "0 2 * * * cd $PROJECT_PATH && $VENV_PATH/bin/python manage.py fetch_jobs >> /tmp/job_fetch.log 2>&1"
        echo ""
        echo "Or every 6 hours:"
        echo "0 */6 * * * cd $PROJECT_PATH && $VENV_PATH/bin/python manage.py fetch_jobs >> /tmp/job_fetch.log 2>&1"
        ;;
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "Setup complete! Make sure to test the fetch command:"
echo "  python manage.py fetch_jobs"
