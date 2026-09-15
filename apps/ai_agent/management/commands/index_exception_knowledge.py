from django.core.management.base import BaseCommand

from apps.ai_agent.rag.indexing import index_all_resolved_exceptions


class Command(BaseCommand):
    help = "Embed resolved/rejected exceptions into KnowledgeChunk for RAG."

    def handle(self, *args, **options):
        count = index_all_resolved_exceptions()
        self.stdout.write(self.style.SUCCESS(f"Indexed {count} exception knowledge chunk(s)."))
