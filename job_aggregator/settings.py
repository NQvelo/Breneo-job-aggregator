import os
from pathlib import Path

# ---------------------------
# BASE DIRECTORY
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

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
    ".onrender.com",  # allow all subdomains of onrender.com
]

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

    # Your apps
    'jobs',
]

# ---------------------------
# MIDDLEWARE
# ---------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

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
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
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
STATIC_ROOT = BASE_DIR / 'staticfiles'  # required for collectstatic

# Optional: extra static folders
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

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
    ]
}
