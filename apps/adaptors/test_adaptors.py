from decimal import Decimal
import io
from datetime import datetime, timezone
from django.test import TestCase


from apps.adaptors.base import CanonicalRecord, DataSourceAdapter
from apps.adaptors.csv_adapter import CsvAdapter
from apps.adaptors.registry import get_adapter, register_adapter, list_registered_adapters
from apps.ingestion.models import RawRecord
from apps.reconciliation.models import Transaction, save_canonical_records


class TestCanonicalRecord(TestCase):
    def test_signed_amount_calculation_credit(self):
        record = CanonicalRecord(
            source_id="test_source",
            external_ref="TXN-001",
            cr_amount=Decimal("1500.50"),
            dr_amount=Decimal("0.00"),
            timestamp=datetime.now(timezone.utc),
        )
        self.assertEqual(record.cr_amount, Decimal("1500.50"))
        self.assertEqual(record.dr_amount, Decimal("0.00"))
        self.assertEqual(record.amount, Decimal("1500.50"))  # Positive for Credit

    def test_signed_amount_calculation_debit(self):
        record = CanonicalRecord(
            source_id="test_source",
            external_ref="TXN-002",
            cr_amount=Decimal("0.00"),
            dr_amount=Decimal("750.25"),
            timestamp=datetime.now(timezone.utc),
        )
        self.assertEqual(record.cr_amount, Decimal("0.00"))
        self.assertEqual(record.dr_amount, Decimal("750.25"))
        self.assertEqual(record.amount, Decimal("-750.25"))  # Negative for Debit

    def test_negative_cr_or_dr_amount_raises_error(self):
        with self.assertRaises(Exception):
            CanonicalRecord(
                source_id="test_source",
                external_ref="TXN-ERR",
                cr_amount=Decimal("-100.00"),
                dr_amount=Decimal("0.00"),
                timestamp=datetime.now(timezone.utc),
            )


class TestAdapterRegistry(TestCase):
    def test_csv_adapter_registered(self):
        adapter_cls = get_adapter("csv")
        self.assertEqual(adapter_cls, CsvAdapter)
        self.assertIn("csv", list_registered_adapters())

    def test_unregistered_adapter_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            get_adapter("non_existent_adapter")
        self.assertIn("No adapter registered for source type 'non_existent_adapter'", str(ctx.exception))


class TestCsvAdapter(TestCase):
    def setUp(self):
        self.adapter = CsvAdapter()

    def test_csv_extraction_and_normalization_with_currency_symbols(self):
        sample_csv = (
            "TXN_ID,TRANS_DATE,CREDIT_AMT,DEBIT_AMT,NARRATIVE,CURRENCY\n"
            "TXN1001,2026-09-12T10:00:00Z,\"₨4,501,558.57\",0.00,Client Payment,INR\n"
            "TXN1002,2026-09-12T10:05:00Z,0.00,\"₨501,558.57\",Vendor Payout,INR\n"
        )

        rows = list(self.adapter.extract(io.StringIO(sample_csv)))
        self.assertEqual(len(rows), 2)

        rec1 = self.adapter.normalize(rows[0], source_id="gl_feed")
        self.assertEqual(rec1.external_ref, "TXN1001")
        self.assertEqual(rec1.cr_amount, Decimal("4501558.57"))
        self.assertEqual(rec1.dr_amount, Decimal("0.00"))
        self.assertEqual(rec1.amount, Decimal("4501558.57"))
        self.assertEqual(rec1.description, "Client Payment")

        rec2 = self.adapter.normalize(rows[1], source_id="gl_feed")
        self.assertEqual(rec2.external_ref, "TXN1002")
        self.assertEqual(rec2.cr_amount, Decimal("0.00"))
        self.assertEqual(rec2.dr_amount, Decimal("501558.57"))
        self.assertEqual(rec2.amount, Decimal("-501558.57"))

    def test_single_amount_column_with_dc_flag(self):
        sample_csv = (
            "VOUCHER_NO,DATE,AMOUNT,DC_FLAG,MEMO\n"
            "V-991,2026-09-12,12500.00,CR,Fee collected\n"
            "V-992,2026-09-12,3200.00,DR,Refund processed\n"
        )

        rows = list(self.adapter.extract(io.StringIO(sample_csv)))
        records = [self.adapter.normalize(r, source_id="bank_b") for r in rows]

        self.assertEqual(records[0].cr_amount, Decimal("12500.00"))
        self.assertEqual(records[0].dr_amount, Decimal("0.00"))
        self.assertEqual(records[0].amount, Decimal("12500.00"))

        self.assertEqual(records[1].cr_amount, Decimal("0.00"))
        self.assertEqual(records[1].dr_amount, Decimal("3200.00"))
        self.assertEqual(records[1].amount, Decimal("-3200.00"))

    def test_extracts_semicolon_delimited_csv(self):
        sample_csv = (
            '"age";"job";"y"\n'
            '"30";"admin.";"yes"\n'
        )
        rows = list(self.adapter.extract(io.StringIO(sample_csv)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0].keys()), {"age", "job", "y"})
        self.assertEqual(rows[0]["age"], "30")


class TestIngestionAndPersistence(TestCase):
    def test_end_to_end_ingest_and_save(self):
        sample_csv = (
            "TXN_ID,TRANS_DATE,CREDIT_AMT,DEBIT_AMT,NARRATIVE\n"
            "TXN-01,2026-09-12,10000.00,0.00,Deposit A\n"
            "TXN-02,2026-09-12,0.00,4000.00,Withdrawal B\n"
            "TXN-03,2026-09-12,2500.00,0.00,Deposit C\n"
        )
        adapter = get_adapter("csv")()

        # 1. Extract raw rows & Stage in RawRecord table
        raw_rows = list(adapter.extract(io.StringIO(sample_csv)))
        raw_instances = [
            RawRecord.objects.create(
                source_type="csv",
                source_id="test_ingest",
                raw_payload=r,
                status="PENDING"
            )
            for r in raw_rows
        ]
        self.assertEqual(RawRecord.objects.count(), 3)

        # 2. Normalize raw records into CanonicalRecord contracts
        canonical_list = [adapter.normalize(r.raw_payload, source_id=r.source_id) for r in raw_instances]
        self.assertEqual(len(canonical_list), 3)

        # 3. Save canonical records to Transaction database
        saved_txs = save_canonical_records(canonical_list)
        self.assertEqual(Transaction.objects.count(), 3)

        # 4. Verify Signed Net Amount Sum
        total_cr = sum(tx.cr_amount for tx in saved_txs)
        total_dr = sum(tx.dr_amount for tx in saved_txs)
        net_sum = sum(tx.amount for tx in saved_txs)

        self.assertEqual(total_cr, Decimal("12500.00"))
        self.assertEqual(total_dr, Decimal("4000.00"))
        self.assertEqual(net_sum, Decimal("8500.00"))
        self.assertEqual(net_sum, total_cr - total_dr)

    def test_large_dataset_20629_rows_normalization(self):
        """Test batch normalization of 20,629 records matching exact net balance ₨4,501,558.57."""
        adapter = CsvAdapter()

        # Build 20,629 CSV rows: 10,000 credits of 500.00, 10,628 debits of 47.00, 1 final adjustment credit of 1,558.57
        # Net sum: (10000 * 500.00) - (10628 * 47.00) + 1558.57 = 5,000,000.00 - 499,516.00 + 1,558.57 = 4,502,042.57...
        # Let's calibrate: 10,000 * 500.00 = 5,000,000.00 credit.
        # Debits: 10,628 * 47.00 = 499,516.00 debit.
        # 5000000.00 - 499516.00 = 4500484.00 net.
        # Plus 1 final credit row of 1074.57 -> 4,501,558.57 net balance!
        lines = ["TXN_ID,TRANS_DATE,CREDIT_AMT,DEBIT_AMT,NARRATIVE,CURRENCY"]
        for i in range(10000):
            lines.append(f"CR-{i},2026-09-12,500.00,0.00,Credit Txn {i},INR")
        for i in range(10628):
            lines.append(f"DR-{i},2026-09-12,0.00,47.00,Debit Txn {i},INR")
        lines.append("CR-LAST,2026-09-12,1074.57,0.00,Adjustment Credit,INR")

        csv_content = "\n".join(lines)
        raw_rows = list(adapter.extract(io.StringIO(csv_content)))
        self.assertEqual(len(raw_rows), 20629)

        # Process and normalize into CanonicalRecords
        canonical_records = [adapter.normalize(r, source_id="large_batch") for r in raw_rows]
        self.assertEqual(len(canonical_records), 20629)

        # Save to Transaction database
        saved_txs = save_canonical_records(canonical_records)
        self.assertEqual(len(saved_txs), 20629)

        # Calculate total signed net amount
        net_balance = sum(tx.amount for tx in saved_txs)
        self.assertEqual(net_balance, Decimal("4501558.57"))

