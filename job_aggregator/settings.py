import os
from pathlib import Path

# ---------------------------
# BASE DIRECTORY
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
CORS_ALLOW_ALL_ORIGINS = True

# Optional: LinkedIn has no public job API. To use a third-party LinkedIn jobs API (e.g. SerpAPI, Apify),
# set LINKEDIN_JOBS_API_URL (and optionally LINKEDIN_JOBS_API_KEY) and add a company with platform="linkedin".
LINKEDIN_JOBS_API_URL = os.environ.get("LINKEDIN_JOBS_API_URL", "")
LINKEDIN_JOBS_API_KEY = os.environ.get("LINKEDIN_JOBS_API_KEY", "")

# ---------------------------
# SECURITY
# ---------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-dev-key-change-in-production"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "localhost:8081",
    ".onrender.com",
    "dashboard.breneo.app",
    ".railway.app",  # Add generic railway support
]

# Domains that are allowed for CSRF-protected requests (e.g. Django admin on Railway)
CSRF_TRUSTED_ORIGINS = [
    "https://breneo-job-aggregator.up.railway.app",
]

allowed_hosts_env = os.environ.get("ALLOWED_HOSTS")
if allowed_hosts_env:
    if allowed_hosts_env == "*":
        ALLOWED_HOSTS = ["*"]
    else:
        ALLOWED_HOSTS.extend(allowed_hosts_env.split(","))

# ---------------------------
# INSTALLED APPS
# ---------------------------
INSTALLED_APPS = [
    # Django default apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'drf_spectacular',

    # Your apps
    'jobs',
    'corsheaders',   # 👈 REQUIRED

]

# ---------------------------
# MIDDLEWARE
# ---------------------------
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
]
try:
    import whitenoise  # noqa: F401
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
except ImportError:
    pass
MIDDLEWARE.extend([
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
])

# ---------------------------
# URLS & WSGI
# ---------------------------
ROOT_URLCONF = 'job_aggregator.urls'
WSGI_APPLICATION = 'job_aggregator.wsgi.application'

# ---------------------------
# TEMPLATES
# ---------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # optional templates folder
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ---------------------------
# DATABASE
# ---------------------------
# Use DATABASE_URL from environment if available (Render PostgreSQL)
# Otherwise, fall back to SQLite for local development
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Render PostgreSQL (production)
    # Import dj_database_url only when DATABASE_URL is set
    try:
        import dj_database_url
        DATABASES = {
            'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
        }
    except ImportError:
        # If dj_database_url is not installed, fall back to manual parsing or SQLite
        # This should not happen in production, but provides a safety fallback
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
                'OPTIONS': {'timeout': 20},
            }
        }
else:
    # SQLite (local development)
    # timeout: wait up to 20s if DB is locked (e.g. fetch_jobs or admin save)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 20,
            },
        }
    }

# ---------------------------
# PASSWORD VALIDATORS
# ---------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------
# INTERNATIONALIZATION
# ---------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ---------------------------
# STATIC & MEDIA FILES
# ---------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise for serving static files in production (optional - only if installed)
try:
    import whitenoise  # noqa: F401
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
except ImportError:
    pass

# Optional: extra static folders (only if directory exists)
_static_dir = BASE_DIR / 'static'
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------
# DEFAULT AUTO FIELD
# ---------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------
# REST FRAMEWORK
# ---------------------------
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'jobs.exceptions.custom_exception_handler',
}

CORS_ALLOW_ALL_ORIGINS = True
