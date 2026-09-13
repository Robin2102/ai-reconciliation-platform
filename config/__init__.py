# Importing celery_app here makes `@shared_task` autodiscover work across apps.
from .celery import app as celery_app
__all__ = ("celery_app",)
