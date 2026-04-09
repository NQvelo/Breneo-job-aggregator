import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

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

_CLOUDINARY_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
if _CLOUDINARY_NAME:
    _idx = INSTALLED_APPS.index("django.contrib.staticfiles") + 1
    INSTALLED_APPS = (
        INSTALLED_APPS[:_idx]
        + ["cloudinary_storage", "cloudinary"]
        + INSTALLED_APPS[_idx:]
    )
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": _CLOUDINARY_NAME,
        "API_KEY": os.environ.get("CLOUDINARY_API_KEY", ""),
        "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", ""),
    }
    CLOUDINARY_URL = (
        f"cloudinary://{CLOUDINARY_STORAGE['API_KEY']}:"
        f"{CLOUDINARY_STORAGE['API_SECRET']}@{CLOUDINARY_STORAGE['CLOUD_NAME']}"
    )
    DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

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
# Railway Postgres often sets DATABASE_URL (host *.railway.internal, in-VPC only) and
# DATABASE_PUBLIC_URL (public proxy). Local `railway shell` uses the same DATABASE_URL;
# private DNS usually does not resolve on your laptop. We detect that with getaddrinfo and
# switch to DATABASE_PUBLIC_URL when needed (deployed containers resolve internal DNS).


def _database_hostname(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def _railway_internal_db_resolves(url: str) -> bool:
    """True if the DB host in url resolves (e.g. on Railway’s network)."""
    host = _database_hostname(url)
    if not host or "railway.internal" not in host:
        return True
    port = urlparse(url).port or 5432
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False
    return True


_private_db = (os.environ.get("DATABASE_URL") or "").strip()
_public_db = (os.environ.get("DATABASE_PUBLIC_URL") or "").strip()
if not _public_db:
    _public_db = (os.environ.get("RAILWAY_DATABASE_PUBLIC_URL") or "").strip()

_internal_unresolvable = (
    _private_db
    and "railway.internal" in _private_db
    and not _railway_internal_db_resolves(_private_db)
)

if _internal_unresolvable and _public_db:
    DATABASE_URL = _public_db
elif _internal_unresolvable and not _public_db:
    raise ImproperlyConfigured(
        "DATABASE_URL uses *.railway.internal, which does not resolve on this machine, and "
        "DATABASE_PUBLIC_URL is not set.\n\n"
        "Fix (pick one):\n"
        "  • Railway → Postgres service → Variables → reference DATABASE_PUBLIC_URL on your "
        "web service (same variable name), then run migrate again.\n"
        "  • Or run: export DATABASE_URL=\"$DATABASE_PUBLIC_URL\" after copying the public "
        "URL from the Postgres service.\n"
        "  • Or run migrations from Railway dashboard → your web service → Shell (inside "
        "Railway, internal DNS works)."
    )
elif _private_db:
    DATABASE_URL = _private_db
else:
    DATABASE_URL = _public_db

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
    # Public job APIs do not use JWT/Bearer; be explicit so deploys never require auth by mistake.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
}

CORS_ALLOW_ALL_ORIGINS = True
