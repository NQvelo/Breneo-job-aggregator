# How to Deploy to Railway

This guide assumes you have a Railway account. If not, sign up at [railway.app](https://railway.app/).

## 1. Prepare Your Project (Already Done)
I have already added the necessary configuration files for you:
- `Procfile`: Tells Railway how to start the app (`gunicorn job_aggregator.wsgi`).
- `runtime.txt`: Tells Railway which Python version to use (`3.11.9`).
- `requirements.txt`: Lists all dependencies.

## 2. Connect GitHub to Railway
1. Log in to your Railway Dashboard.
2. Click **"New Project"**.
3. Select **"Deploy from GitHub repo"**.
4. Choose your repository (`job-aggregator`) from the list.
5. Click **"Deploy Now"**.

## 3. Configure Environment Variables
Once the project is created, go to the **Variables** tab in your service and add the following:

| Variable Name | Value | Description |
|or|or|or|
| `DJANGO_SECRET_KEY` | (Generate a random string) | Security key for Django. |
| `DJANGO_DEBUG` | `False` | Run in production mode. |
| `ALLOWED_HOSTS` | `*` | Allows Railway domain to access the app. |
| `DISABLE_COLLECTSTATIC` | `0` | Ensures static files are collected. |

> **Note:** If you are using a database, you can add a generic PostgreSQL service in Railway and link it. Railway will automatically provide a `DATABASE_URL` variable.

## 4. Finalize Deployment
1. Railway will automatically detect the changes and rebuild.
2. Go to the **Settings** tab.
3. Under **Networking**, click **"Generate Domain"** to get a public URL (e.g., `job-aggregator-production.up.railway.app`).
4. Visit that URL to see your live API!

## Troubleshooting
- **Logs:** Check the **Deployments** > **View Logs** tab if anything fails.
- **Static Files:** If CSS is missing, ensure `whitenoise` is configured (it is already set up in `settings.py`).
