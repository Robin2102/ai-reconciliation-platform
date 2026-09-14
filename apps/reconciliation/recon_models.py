"""Reconciliation project models (Phase 5A): two legs, runs, match pairs."""

from __future__ import annotations

from django.db import models


class ReconProject(models.Model):
    """
    Named job comparing two ingested datasets (source leg vs target leg).

    Each leg points at a completed IngestFile; matching runs on Transaction rows.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        ERROR = "error", "Error"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.name

    def source_leg(self) -> ReconLeg | None:
        return self.legs.filter(role=ReconLeg.Role.SOURCE).first()

    def target_leg(self) -> ReconLeg | None:
        return self.legs.filter(role=ReconLeg.Role.TARGET).first()


class MatchRule(models.Model):
    """
    Configurable match rule (Phase 5B).

    `definition` JSON holds conditions (simple or if/else). Evaluated in priority order.
    """

    class Cardinality(models.TextChoices):
        ONE_TO_ONE = "one_to_one", "1:1"

    class LogicMode(models.TextChoices):
        SIMPLE = "simple", "Simple"
        IF_ELSE = "if_else", "If / else"

    class Action(models.TextChoices):
        MARK_MATCHED = "mark_matched", "Mark as match"

    project = models.ForeignKey(ReconProject, related_name="rules", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    priority = models.PositiveIntegerField(default=10, help_text="Lower runs first.")
    cardinality = models.CharField(
        max_length=20, choices=Cardinality.choices, default=Cardinality.ONE_TO_ONE
    )
    action = models.CharField(max_length=30, choices=Action.choices, default=Action.MARK_MATCHED)
    logic_mode = models.CharField(max_length=20, choices=LogicMode.choices, default=LogicMode.SIMPLE)
    definition = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "id"]

    def __str__(self) -> str:
        return f"{self.name} (p{self.priority})"


class ReconLeg(models.Model):
    """One side of a project — ties a done ingest upload to the project."""

    class Role(models.TextChoices):
        SOURCE = "source", "Source"
        TARGET = "target", "Target"

    project = models.ForeignKey(ReconProject, related_name="legs", on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=Role.choices)
    ingest_file = models.ForeignKey("ingestion.IngestFile", on_delete=models.PROTECT)
    feed_key = models.CharField(max_length=100, help_text="Copy of ingest source_id for display")
    row_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "role"], name="uniq_recon_leg_role_per_project"),
        ]

    def __str__(self) -> str:
        return f"{self.project.name} {self.role}"


class ReconRun(models.Model):
    """One execution of the matching engine for a project."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        ERROR = "error", "Error"

    project = models.ForeignKey(ReconProject, related_name="runs", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"Run {self.pk} ({self.project.name})"


class MatchResult(models.Model):
    """A paired source/target transaction from a successful match."""

    class Status(models.TextChoices):
        MATCHED = "matched", "Matched"

    run = models.ForeignKey(ReconRun, related_name="results", on_delete=models.CASCADE)
    source_transaction = models.ForeignKey(
        "reconciliation.Transaction",
        related_name="match_results_as_source",
        on_delete=models.CASCADE,
    )
    target_transaction = models.ForeignKey(
        "reconciliation.Transaction",
        related_name="match_results_as_target",
        on_delete=models.CASCADE,
    )
    confidence = models.DecimalField(max_digits=5, decimal_places=4, default=1)
    rule_name = models.CharField(max_length=80, default="exact_1_1")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.MATCHED)
    explanation = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]
