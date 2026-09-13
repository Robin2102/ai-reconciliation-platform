"""
CONCEPT TO LEARN: Django settings, environment-based config, and how
INSTALLED_APPS / DATABASES / CELERY / REST_FRAMEWORK tie the whole
project together.

TODO (do this together, step by step):
- SECRET_KEY / DEBUG from environment variables (never hardcode in real use)
- DATABASES: point at the `postgres` service from docker-compose.yml
- INSTALLED_APPS: add 'rest_framework', 'apps.core', 'apps.adaptors',
  'apps.ingestion', 'apps.reconciliation', 'apps.exceptions', 'apps.ai_agent'
- CELERY_BROKER_URL / CELERY_RESULT_BACKEND -> redis://redis:6379/0
- KAFKA_BOOTSTRAP_SERVERS -> "kafka:9092"
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-learning-key-recon-platform-2026")

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.adaptors",
    "apps.ingestion",
    "apps.reconciliation",
    "apps.exceptions",
    "apps.ai_agent",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

STATIC_URL = "/static/"


