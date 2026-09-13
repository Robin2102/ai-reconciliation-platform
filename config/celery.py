"""
Celery app for this Django project.

CELERY_* settings map to Celery config (broker_url, result_backend, …).
autodiscover_tasks() loads tasks.py in each INSTALLED_APPS package.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("reconciliation")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
