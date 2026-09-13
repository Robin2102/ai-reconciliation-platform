"""
CONCEPT TO LEARN: how Celery discovers tasks across Django apps, and the
difference between the BROKER (Redis, holds pending tasks) and the
RESULT BACKEND (where task results are stored).

TODO (together): wire this up to config.settings and call app.autodiscover_tasks()
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("reconciliation")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

