from pathlib import Path

from pydantic import ValidationError
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ingestion.serializers import IngestUploadSerializer
from apps.ingestion.services import ingest_upload


class IngestUploadView(APIView):
    """
    POST /api/ingest/ — multipart file + source_type + optional source_id.

    Phase 2: synchronous 201 so you can see rows without a worker.
    Phase 3: same service, called via Celery, response 202.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = IngestUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded = serializer.validated_data["file"]
        source_type = serializer.validated_data["source_type"]
        source_id = serializer.validated_data.get("source_id") or Path(uploaded.name).stem

        try:
            result = ingest_upload(source_type, source_id, uploaded)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as exc:
            return Response(
                {"detail": "Canonical record validation failed.", "errors": exc.errors()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(result, status=status.HTTP_201_CREATED)
