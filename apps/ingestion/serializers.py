from rest_framework import serializers


class IngestUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    source_type = serializers.CharField(max_length=50, default="csv")
    source_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
