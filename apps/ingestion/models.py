from django.db import models


class RawRecord(models.Model):
    """
    Staging table for raw untouched ingested payloads.
    Stores raw rows prior to normalization for audit trails and replay-ability.
    """
    source_type = models.CharField(max_length=50, help_text="Adapter type name (e.g., 'csv', 'rest_api')")
    source_id = models.CharField(max_length=100, db_index=True, help_text="Identifier for the source dataset/file")
    raw_payload = models.JSONField(help_text="Untouched raw payload dictionary")
    ingested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="PENDING", help_text="Processing status (PENDING, NORMALIZED, ERROR)")

    class Meta:
        ordering = ["-ingested_at"]
        verbose_name = "Raw Record"
        verbose_name_plural = "Raw Records"

    def __str__(self):
        return f"RawRecord({self.source_type}:{self.source_id} - {self.id})"

