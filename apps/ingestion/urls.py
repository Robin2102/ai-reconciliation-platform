from django.urls import path

from apps.ingestion.views import IngestUploadView

urlpatterns = [
    path("ingest/", IngestUploadView.as_view(), name="ingest-upload"),
]
