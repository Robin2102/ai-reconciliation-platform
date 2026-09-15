from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.connectors.crypto import decrypt_secrets, encrypt_secrets


class Connector(models.Model):
    class ConnectorType(models.TextChoices):
        LOCAL_DIRECTORY = "local_directory", "Local directory"
        SFTP = "sftp", "SFTP (coming soon)"
        POSTGRES = "postgres", "PostgreSQL (coming soon)"

    name = models.CharField(max_length=200)
    connector_type = models.CharField(
        max_length=40,
        choices=ConnectorType.choices,
        default=ConnectorType.LOCAL_DIRECTORY,
    )
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    secrets_ciphertext = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="connectors_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.connector_type})"

    def set_secrets(self, data: dict) -> None:
        self.secrets_ciphertext = encrypt_secrets(data)

    def get_secrets(self) -> dict:
        return decrypt_secrets(self.secrets_ciphertext)

    @property
    def secrets_configured(self) -> bool:
        return bool(self.secrets_ciphertext)


class SourceDefinition(models.Model):
    """Logical feed (maps to reconciliation `source_id` and MappingTemplate)."""

    class FileSelectionMode(models.TextChoices):
        EXPLICIT_PATHS = "explicit_paths", "Explicit file paths"
        GLOB = "glob", "Glob (future)"
        POSTGRES_QUERY = "postgres_query", "Postgres query (future)"

    source_id = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    default_source_type = models.CharField(max_length=50, default="csv")
    connector = models.ForeignKey(
        Connector,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sources",
    )
    mapping_template = models.ForeignKey(
        "ingestion.MappingTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_definitions",
    )
    file_selection_mode = models.CharField(
        max_length=30,
        choices=FileSelectionMode.choices,
        default=FileSelectionMode.EXPLICIT_PATHS,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.source_id})"


class SourceFileSpec(models.Model):
    source = models.ForeignKey(SourceDefinition, related_name="file_specs", on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    remote_path = models.CharField(max_length=500)
    glob_pattern = models.CharField(max_length=200, blank=True, default="")
    postgres_query = models.TextField(blank=True, default="")
    filename_hint = models.CharField(max_length=255, blank=True, default="")
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["source", "remote_path"], name="uniq_source_remote_path"),
        ]

    def __str__(self) -> str:
        return self.remote_path
