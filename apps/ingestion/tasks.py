"""
CONCEPT TO LEARN: Celery tasks + why ingestion is async, not inline in a view.

Flow to build together:
1. A view/endpoint (or a scheduled beat task) triggers `ingest_source.delay(source_type)`
2. The Celery task gets the right adaptor from the registry, extracts + normalizes
3. Each normalized record is saved to the RawRecord staging table
4. The task PRODUCES a Kafka event ("record.ingested") so downstream reconciliation
   can react without ingestion and reconciliation being tightly coupled.
"""
# from celery import shared_task
# from apps.adaptors.registry import get_adapter

# @shared_task
# def ingest_source(source_type: str):
#     """TODO (together)."""
#     ...
