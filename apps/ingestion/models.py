from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django.db.models.manager import Manager


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
    ingest_file = models.ForeignKey(
        "IngestFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="raw_records",
    )

    class Meta:
        ordering = ["-ingested_at"]
        verbose_name = "Raw Record"
        verbose_name_plural = "Raw Records"

    def __str__(self):
        return f"RawRecord({self.source_type}:{self.source_id} - {self.id})"


class IngestFile(models.Model):
    class Status(models.TextChoices):
        STAGED = "staged"
        MAPPED = "mapped"
        INGESTING = "ingesting"
        DONE = "done"
        ERROR = "error"

    path = models.CharField(max_length=500)
    original_name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=50, default="csv")
    source_id = models.CharField(max_length=100, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STAGED)
    error_message = models.TextField(blank=True, default="")
    source_definition = models.ForeignKey(
        "connectors.SourceDefinition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingest_files",
    )
    job_run = models.ForeignKey(
        "ingestion.IngestionJobRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingest_files",
    )
    connector_fetch_path = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"IngestFile({self.original_name} {self.status})"


class MappingTemplate(models.Model):
    name = models.CharField(max_length=200)
    source_id = models.CharField(max_length=100, db_index=True)
    normalize_headers = models.BooleanField(default=True)
    default_currency = models.CharField(max_length=10, default="INR")
    dedupe = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        columns: Manager["ColumnMapping"]

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"MappingTemplate({self.name} / {self.source_id})"


class ColumnMapping(models.Model):
    class DetectedType(models.TextChoices):
        STRING = "string"
        DATE = "date"
        DECIMAL = "decimal"
        INTEGER = "integer"

    class Role(models.TextChoices):
        NONE = "none"
        EXTERNAL_REF = "external_ref"
        TIMESTAMP = "timestamp"
        DATE_YEAR = "date_year"
        DATE_MONTH = "date_month"
        DATE_DAY = "date_day"
        TIME = "time"
        CR_AMOUNT = "cr_amount"
        DR_AMOUNT = "dr_amount"
        AMOUNT = "amount"
        TXN_TYPE = "txn_type"
        CURRENCY = "currency"
        DESCRIPTION = "description"
        IGNORE = "ignore"

    class NullPolicy(models.TextChoices):
        KEEP = "keep"
        EMPTY_AS_NULL = "empty_as_null"

    class Pii(models.TextChoices):
        NONE = "none"
        ENCRYPT = "encrypt"

    template = models.ForeignKey(MappingTemplate, related_name="columns", on_delete=models.CASCADE)
    source_header = models.CharField(max_length=1024)
    detected_type = models.CharField(max_length=20, choices=DetectedType.choices, default=DetectedType.STRING)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.NONE)
    mapped_name = models.CharField(max_length=1024, blank=True, default="")
    null_policy = models.CharField(max_length=20, choices=NullPolicy.choices, default=NullPolicy.KEEP)
    date_format = models.CharField(max_length=40, blank=True, default="")
    pii = models.CharField(max_length=20, choices=Pii.choices, default=Pii.NONE)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]
        unique_together = [("template", "source_header")]

    def __str__(self):
        return f"{self.source_header} → {self.role}"


class IngestionJob(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready to run"

    name = models.CharField(max_length=200)
    source_id = models.CharField(max_length=100, db_index=True, default="")
    default_source_type = models.CharField(max_length=50, default="csv")
    connector = models.ForeignKey(
        "connectors.Connector",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingestion_jobs",
    )
    source_definition = models.ForeignKey(
        "connectors.SourceDefinition",
        null=True,
        blank=True,
        related_name="ingestion_jobs",
        on_delete=models.SET_NULL,
    )
    template = models.ForeignKey(
        MappingTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingestion_jobs",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    profile_local_path = models.CharField(max_length=500, blank=True, default="")
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_run_at", "name"]

    def __str__(self) -> str:
        return self.name


class IngestionJobInput(models.Model):
    """Up to MAX_INGESTION_JOB_FILES inputs per job (upload path or connector remote path)."""

    job = models.ForeignKey(IngestionJob, related_name="inputs", on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    remote_path = models.CharField(max_length=500, blank=True, default="")
    local_path = models.CharField(max_length=500, blank=True, default="")
    original_filename = models.CharField(max_length=255, blank=True, default="")
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]


class IngestionJobRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        ERROR = "error", "Error"

    job = models.ForeignKey(IngestionJob, related_name="runs", on_delete=models.CASCADE)
    primary_ingest_file = models.ForeignKey(
        IngestFile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="primary_job_run",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at", "-id"]


class IngestionJobFile(models.Model):
    class FetchStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        FETCHED = "fetched", "Fetched"
        SKIPPED = "skipped", "Skipped"
        ERROR = "error", "Error"

    run = models.ForeignKey(IngestionJobRun, related_name="job_files", on_delete=models.CASCADE)
    source_file_spec = models.ForeignKey(
        "connectors.SourceFileSpec",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    ingest_file = models.ForeignKey(
        IngestFile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="job_files",
    )
    remote_path = models.CharField(max_length=500)
    fetch_status = models.CharField(
        max_length=20, choices=FetchStatus.choices, default=FetchStatus.PENDING
    )
    error_message = models.TextField(blank=True, default="")
