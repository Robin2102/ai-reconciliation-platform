"""
CONCEPT TO LEARN: a consumer is a LONG-RUNNING process (not a Celery task
triggered by a request) — usually run as its own management command or
worker process, continuously polling Kafka.

TODO (together): a Django management command `consume_ingestion_events`
that listens on 'record.ingested' and triggers reconciliation matching.
"""
