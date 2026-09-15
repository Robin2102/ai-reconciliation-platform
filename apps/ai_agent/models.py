from django.db import models


class KnowledgeChunk(models.Model):
    """Embedded text for RAG (resolved exceptions, policies)."""

    class Kind(models.TextChoices):
        RESOLVED_EXCEPTION = "resolved_exception", "Resolved exception"
        POLICY = "policy", "Policy / playbook"

    kind = models.CharField(max_length=40, choices=Kind.choices, default=Kind.RESOLVED_EXCEPTION)
    exception = models.OneToOneField(
        "exceptions.ExceptionRecord",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="knowledge_chunk",
    )
    project_id = models.IntegerField(null=True, blank=True, db_index=True)
    text = models.TextField(help_text="Retrieval document (no raw PII payloads).")
    embedding = models.JSONField(
        default=list,
        help_text="Dense vector stored as JSON (pgvector optional later).",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"KnowledgeChunk({self.kind} #{self.pk})"
