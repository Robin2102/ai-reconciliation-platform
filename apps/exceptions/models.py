"""Exception queue: transactions that did not match in a reconciliation run."""

from __future__ import annotations

from django.db import models


class ExceptionRecord(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"

    class Side(models.TextChoices):
        SOURCE = "source", "Source"
        TARGET = "target", "Target"

    project = models.ForeignKey(
        "reconciliation.ReconProject",
        related_name="exceptions",
        on_delete=models.CASCADE,
    )
    run = models.ForeignKey(
        "reconciliation.ReconRun",
        related_name="exceptions",
        on_delete=models.CASCADE,
    )
    transaction = models.ForeignKey(
        "reconciliation.Transaction",
        on_delete=models.CASCADE,
        related_name="exception_records",
    )
    side = models.CharField(max_length=10, choices=Side.choices)
    reason = models.CharField(max_length=200, default="unmatched")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolution_note = models.TextField(blank=True, default="")
    ai_suggestion = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Exception({self.side} tx={self.transaction_id} {self.status})"
