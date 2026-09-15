"""Ingestion job run entrypoint (merged multi-file ingest)."""

from __future__ import annotations

from apps.ingestion.merged_ingest import execute_merged_ingestion_run


def execute_ingestion_job_run(run):
    return execute_merged_ingestion_run(run)
