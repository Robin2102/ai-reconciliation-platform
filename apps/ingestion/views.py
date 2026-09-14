from pathlib import Path
from typing import Any, cast

from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingestion.serializers import IngestUploadSerializer
from apps.ingestion.tasks import enqueue_ingest_file


class IngestUploadView(APIView):
    """
    POST /api/ingest/ — accept the file, enqueue ingest, return 202.

    Parsing and DB writes run in ingest_file_task (Celery worker).
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = IngestUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        uploaded = data["file"]
        source_type = data["source_type"]
        source_id = data.get("source_id") or Path(uploaded.name).stem

        try:
            task = enqueue_ingest_file(source_type, source_id, uploaded)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "task_id": task.id,
                "status": "queued",
                "source_type": source_type.lower(),
                "source_id": source_id,
            },
            status=status.HTTP_202_ACCEPTED,
        )
