from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from apps.ai_agent.models import KnowledgeChunk
from apps.ai_agent.rag.embeddings import fake_embed
from apps.ai_agent.rag.indexing import index_exception_record
from apps.ai_agent.rag.retriever import retrieve_similar
from apps.ai_agent.tools.tools import retrieve_similar_past_cases
from apps.exceptions.models import ExceptionRecord
from apps.reconciliation.models import Transaction
from apps.reconciliation.recon_models import ReconProject, ReconRun


class RAGTests(TestCase):
    def test_similar_text_scores_higher(self):
        a = fake_embed("narration reference INV-1001 amount mismatch bank")
        b = fake_embed("narration reference INV-1001 write-off timing")
        KnowledgeChunk.objects.create(text="case a", embedding=a, metadata={})
        KnowledgeChunk.objects.create(text="case b", embedding=b, metadata={})
        KnowledgeChunk.objects.create(
            text="case c", embedding=fake_embed("completely unrelated vendor PO-9999"), metadata={}
        )
        hits = retrieve_similar("reference INV-1001 unmatched bank leg", k=1)
        self.assertEqual(len(hits), 1)
        self.assertIn(hits[0].text, {"case a", "case b"})

    def test_index_resolved_exception(self):
        project = ReconProject.objects.create(name="p")
        run = ReconRun.objects.create(project=project, status=ReconRun.Status.DONE)
        tx = Transaction.objects.create(
            source_id="demo-bank",
            external_ref="INV-1001",
            amount="100.00",
            currency="USD",
            timestamp=timezone.make_aware(datetime(2026, 8, 31)),
            cr_amount="100.00",
            dr_amount="0",
        )
        record = ExceptionRecord.objects.create(
            project=project,
            run=run,
            transaction=tx,
            side=ExceptionRecord.Side.SOURCE,
            reason="unmatched",
            status=ExceptionRecord.Status.RESOLVED,
            resolution_kind=ExceptionRecord.ResolutionKind.WRITE_OFF,
            resolution_note="Extract INV-1001 from narration",
        )
        chunk = index_exception_record(record)
        self.assertIsNotNone(chunk)
        self.assertIn("INV-1001", chunk.text)
        hits = retrieve_similar_past_cases("INV-1001 narration", k=1)
        self.assertEqual(len(hits), 1)
