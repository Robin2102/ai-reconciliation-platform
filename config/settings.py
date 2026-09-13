"""
CONCEPT TO LEARN: Django settings from the environment.

- USE_SQLITE=1 (default): local tests and offline work.
- USE_SQLITE=0: compose Postgres (concurrent writers, JSONB, later pgvector).
- CELERY_* and KAFKA_* are wired now so Phase 3–4 do not rewrite settings.
- DEBUG=false refuses the insecure default SECRET_KEY.
- django-monolith/.env is loaded here (does not override vars already in the shell).
- `manage.py test` / pytest always use SQLite so CI stays offline.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-learning-key-recon-platform-2026")
DEBUG = env_bool("DEBUG", True)

if not DEBUG and SECRET_KEY.startswith("django-insecure-"):
    raise RuntimeError("Set SECRET_KEY when DEBUG is false.")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "*").split(",")
    if host.strip()
]

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

# Silk records every request + SQL. Optional: skip if the package is not installed.
if DEBUG:
    try:
        import silk  # noqa: F401
    except ImportError:
        silk = None
    if silk is not None:
        INSTALLED_APPS.append("silk")
        MIDDLEWARE.insert(1, "silk.middleware.SilkyMiddleware")
        SILKY_PYTHON_PROFILER = True
        SILKY_META = True

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

USE_SQLITE = env_bool("USE_SQLITE", True)
RUNNING_TESTS = "test" in sys.argv or os.getenv("PYTEST_CURRENT_TEST") is not None
if RUNNING_TESTS:
    USE_SQLITE = True

if USE_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    # Host from the Mac: localhost. Host from another container: postgres.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "reconciliation"),
            "USER": os.getenv("POSTGRES_USER", "reconciliation"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "reconciliation"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5433"),
        }
    }

# Phase 3 (Celery) and Phase 4 (Kafka) read these; unused until those workers exist.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

STATIC_URL = "/static/"
