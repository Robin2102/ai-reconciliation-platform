from django.core.management.base import BaseCommand

from apps.reconciliation.kafka_consumer import consume_matched_events


class Command(BaseCommand):
    help = "Long-running consumer for Kafka topic record.matched (Phase 5B)."

    def handle(self, *args, **options):
        self.stdout.write("Polling record.matched — Ctrl+C to stop.")
        consume_matched_events()
