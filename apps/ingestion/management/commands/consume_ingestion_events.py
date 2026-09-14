from django.core.management.base import BaseCommand

from apps.ingestion.kafka_consumer import consume_ingestion_events


class Command(BaseCommand):
    help = "Long-running consumer for Kafka topic record.ingested (Phase 4)."

    def handle(self, *args, **options):
        self.stdout.write("Polling record.ingested — Ctrl+C to stop.")
        consume_ingestion_events()
