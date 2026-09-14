import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from apps.ingestion.mapping import apply_column_mapping, validate_template
from apps.ingestion.models import ColumnMapping, MappingTemplate
from apps.ingestion.pii import encrypt_pii
from apps.ingestion.profiling import profile_csv
from apps.ingestion.services import ingest_source

BANK_CSV = (
    "TRAN_ID,TXN_TYPE,AMOUNT,VALUE DATE,CARD_NUMBER,DESCRIPTION\n"
    "T1,C,100.00,13/09/2026,4111111111111111,Shop\n"
    "T2,D,50.00,13/09/2026,4111111111111111,ATM\n"
)


def _write_csv(body: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    handle.write(body)
    handle.close()
    return Path(handle.name)


class ProfilingTests(TestCase):
    def test_profiles_screenshot_style_headers(self):
        path = _write_csv(BANK_CSV)
        try:
            profile = profile_csv(path)
        finally:
            path.unlink(missing_ok=True)
        headers = profile["headers"]
        self.assertEqual(
            headers,
            ["TRAN_ID", "TXN_TYPE", "AMOUNT", "VALUE DATE", "CARD_NUMBER", "DESCRIPTION"],
        )
        by_header = {c["source_header"]: c for c in profile["columns"]}
        self.assertEqual(by_header["TRAN_ID"]["role"], "external_ref")
        self.assertEqual(by_header["TXN_TYPE"]["role"], "txn_type")
        self.assertEqual(by_header["AMOUNT"]["role"], "amount")
        self.assertEqual(by_header["VALUE DATE"]["role"], "timestamp")
        self.assertEqual(by_header["VALUE DATE"]["detected_type"], "date")
        self.assertEqual(by_header["VALUE DATE"]["date_format"], "DD/MM/YYYY")
        self.assertEqual(by_header["CARD_NUMBER"]["pii"], "encrypt")
        self.assertEqual(by_header["DESCRIPTION"]["role"], "description")
        self.assertEqual(len(profile["sample_rows"]), 2)

    def test_does_not_suggest_ymd_when_full_date_column_exists(self):
        path = _write_csv(
            "date,Day,Month,Year,amount\n"
            "2022-01-01,01,01,2022,100\n"
        )
        try:
            profile = profile_csv(path)
        finally:
            path.unlink(missing_ok=True)
        by_header = {c["source_header"]: c for c in profile["columns"]}
        self.assertEqual(by_header["date"]["role"], "timestamp")
        self.assertEqual(by_header["Day"]["role"], "none")
        self.assertEqual(by_header["Month"]["role"], "none")
        self.assertEqual(by_header["Year"]["role"], "none")

    def test_suggests_ymd_and_drcr(self):
        path = _write_csv(
            "name,DrCr,amount,Day,Month,Year\n"
            "ATM,Db,100.00,01,01,2022\n"
        )
        try:
            profile = profile_csv(path)
        finally:
            path.unlink(missing_ok=True)
        by_header = {c["source_header"]: c for c in profile["columns"]}
        self.assertEqual(by_header["DrCr"]["role"], "txn_type")
        self.assertEqual(by_header["Day"]["role"], "date_day")
        self.assertEqual(by_header["Month"]["role"], "date_month")
        self.assertEqual(by_header["Year"]["role"], "date_year")

    def test_profiles_semicolon_delimited_csv(self):
        path = _write_csv(
            '"age";"job";"marital";"y"\n'
            '"30";"admin.";"married";"yes"\n'
        )
        try:
            profile = profile_csv(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(profile["headers"], ["age", "job", "marital", "y"])
        self.assertLess(max(len(h) for h in profile["headers"]), 200)


class MappingApplyTests(TestCase):
    def setUp(self):
        self.template = MappingTemplate.objects.create(
            name="bank",
            source_id="mur-bank",
            default_currency="MUR",
        )
        specs = [
            ("TRAN_ID", "string", "external_ref", "", "none"),
            ("TXN_TYPE", "string", "txn_type", "", "none"),
            ("AMOUNT", "decimal", "amount", "", "none"),
            ("VALUE DATE", "date", "timestamp", "DD/MM/YYYY", "none"),
            ("CARD_NUMBER", "string", "none", "", "encrypt"),
            ("DESCRIPTION", "string", "description", "", "none"),
        ]
        for header, dtype, role, date_fmt, pii in specs:
            ColumnMapping.objects.create(
                template=self.template,
                source_header=header,
                detected_type=dtype,
                role=role,
                mapped_name=header.lower().replace(" ", "_"),
                date_format=date_fmt,
                pii=pii,
                extra={"trim": True},
            )

    def test_amount_and_txn_type_with_default_currency(self):
        row = {
            "TRAN_ID": "T1",
            "TXN_TYPE": "C",
            "AMOUNT": "100.00",
            "VALUE DATE": "13/09/2026",
            "CARD_NUMBER": "4111111111111111",
            "DESCRIPTION": "Shop",
        }
        rec = apply_column_mapping(row, self.template, "mur-bank")
        self.assertEqual(rec.external_ref, "T1")
        self.assertEqual(str(rec.cr_amount), "100.00")
        self.assertEqual(str(rec.dr_amount), "0.00")
        self.assertEqual(rec.currency, "MUR")
        self.assertEqual(rec.description, "Shop")
        self.assertNotEqual(rec.raw_payload["CARD_NUMBER"], "4111111111111111")
        self.assertEqual(rec.raw_payload["CARD_NUMBER__last4"], "1111")
        self.assertTrue(str(rec.raw_payload["CARD_NUMBER"]).startswith("gAAAA"))

    def test_debit_marker(self):
        row = {
            "TRAN_ID": "T2",
            "TXN_TYPE": "D",
            "AMOUNT": "50.00",
            "VALUE DATE": "13/09/2026",
            "CARD_NUMBER": "4111111111111111",
            "DESCRIPTION": "ATM",
        }
        rec = apply_column_mapping(row, self.template, "mur-bank")
        self.assertEqual(str(rec.cr_amount), "0.00")
        self.assertEqual(str(rec.dr_amount), "50.00")
        self.assertEqual(str(rec.amount), "-50.00")

    def test_db_marker_is_debit(self):
        row = {
            "TRAN_ID": "T2",
            "TXN_TYPE": "Db",
            "AMOUNT": "50.00",
            "VALUE DATE": "13/09/2026",
            "CARD_NUMBER": "4111111111111111",
            "DESCRIPTION": "ATM",
        }
        rec = apply_column_mapping(row, self.template, "mur-bank")
        self.assertEqual(str(rec.dr_amount), "50.00")

    def test_split_date_and_time_and_joined_refs(self):
        template = MappingTemplate.objects.create(
            name="split",
            source_id="split-bank",
            default_currency="INR",
        )
        specs = [
            ("name", "external_ref"),
            ("seq", "external_ref"),
            ("Year", "date_year"),
            ("Month", "date_month"),
            ("Day", "date_day"),
            ("Time", "time"),
            ("cash_cr", "cr_amount"),
            ("xfer_cr", "cr_amount"),
            ("debit", "dr_amount"),
        ]
        for header, role in specs:
            ColumnMapping.objects.create(
                template=template,
                source_header=header,
                role=role,
                extra={"trim": True},
            )
        rec = apply_column_mapping(
            {
                "name": "ATM",
                "seq": "99",
                "Year": "2022",
                "Month": "01",
                "Day": "01",
                "Time": "14:05:00",
                "cash_cr": "10.00",
                "xfer_cr": "5.00",
                "debit": "0",
            },
            template,
            "split-bank",
        )
        self.assertEqual(rec.external_ref, "ATM|99")
        self.assertEqual(str(rec.cr_amount), "15.00")
        self.assertEqual(rec.timestamp.year, 2022)
        self.assertEqual(rec.timestamp.month, 1)
        self.assertEqual(rec.timestamp.day, 1)
        self.assertEqual(rec.timestamp.hour, 14)
        self.assertEqual(rec.timestamp.minute, 5)

    def test_infers_db_from_unmapped_drcr_column(self):
        template = MappingTemplate.objects.create(name="infer", source_id="infer", default_currency="INR")
        for header, role in (
            ("name", "external_ref"),
            ("date", "timestamp"),
            ("amount", "amount"),
            ("DrCr", "none"),
        ):
            ColumnMapping.objects.create(
                template=template,
                source_header=header,
                role=role,
                date_format="YYYY-MM-DD" if role == "timestamp" else "",
                extra={"trim": True},
            )
        rec = apply_column_mapping(
            {"name": "ATM", "date": "2022-01-01", "amount": "10000.0", "DrCr": "Db"},
            template,
            "infer",
        )
        self.assertEqual(str(rec.dr_amount), "10000.00")
        self.assertEqual(rec.raw_payload["_generated"]["txn_type"], "DR")
        self.assertEqual(rec.raw_payload["_generated"]["transaction_date"], "2022-01-01")
        self.assertIsNone(rec.raw_payload["_generated"]["reconciled_date"])
        self.assertIsNone(rec.raw_payload["_generated"]["reconciled_by"])

    def test_signed_amount_without_type_column(self):
        template = MappingTemplate.objects.create(name="signed", source_id="signed", default_currency="INR")
        for header, role in (("id", "external_ref"), ("date", "timestamp"), ("amount", "amount")):
            ColumnMapping.objects.create(
                template=template,
                source_header=header,
                role=role,
                date_format="YYYY-MM-DD" if role == "timestamp" else "",
                extra={"trim": True},
            )
        rec = apply_column_mapping(
            {"id": "1", "date": "2022-01-01", "amount": "-40.00"},
            template,
            "signed",
        )
        self.assertEqual(str(rec.dr_amount), "40.00")
        self.assertEqual(rec.raw_payload["_generated"]["txn_type"], "DR")

    def test_pii_ciphertext_persisted_not_plaintext(self):
        path = _write_csv(BANK_CSV)
        try:
            ingest_source("csv", "mur-bank", str(path), template=self.template)
        finally:
            path.unlink(missing_ok=True)
        from apps.ingestion.models import RawRecord
        from apps.reconciliation.models import Transaction

        raw = RawRecord.objects.filter(source_id="mur-bank").order_by("id").first()
        self.assertIsNotNone(raw)
        pan = raw.raw_payload["CARD_NUMBER"]
        self.assertNotEqual(pan, "4111111111111111")
        self.assertNotIn("4111111111111111", str(raw.raw_payload))
        tx = Transaction.objects.get(external_ref="T1")
        self.assertNotEqual(tx.raw_payload["CARD_NUMBER"], "4111111111111111")
        self.assertEqual(tx.raw_payload["_generated"]["txn_type"], "CR")
        self.assertEqual(tx.currency, "MUR")
        self.assertEqual(str(tx.cr_amount), "100.00")


class TimestampParseTests(TestCase):
    def test_iso_date_parses_when_template_format_is_wrong(self):
        template = MappingTemplate.objects.create(name="d", source_id="d", default_currency="INR")
        ColumnMapping.objects.create(
            template=template,
            source_header="date",
            role="timestamp",
            date_format="DD/MM/YYYY",
            extra={"trim": True},
        )
        ColumnMapping.objects.create(template=template, source_header="id", role="external_ref")
        ColumnMapping.objects.create(template=template, source_header="amt", role="amount")
        rec = apply_column_mapping(
            {"id": "1", "date": "2022-01-01", "amt": "10"},
            template,
            "d",
        )
        self.assertEqual(rec.timestamp.year, 2022)
        self.assertEqual(rec.timestamp.month, 1)
        self.assertEqual(rec.timestamp.day, 1)

    def test_compact_yyyymmdd_parses(self):
        template = MappingTemplate.objects.create(name="d", source_id="compact", default_currency="INR")
        ColumnMapping.objects.create(
            template=template,
            source_header="F_TRANDATE",
            role="timestamp",
            date_format="YYYY-MM-DD",
            extra={"trim": True},
        )
        ColumnMapping.objects.create(template=template, source_header="id", role="external_ref")
        ColumnMapping.objects.create(template=template, source_header="amt", role="amount")
        rec = apply_column_mapping(
            {"id": "1", "F_TRANDATE": "20260508", "amt": "10"},
            template,
            "compact",
        )
        self.assertEqual(rec.timestamp.year, 2026)
        self.assertEqual(rec.timestamp.month, 5)
        self.assertEqual(rec.timestamp.day, 8)


class ValidateTemplateTests(TestCase):
    def test_ref_and_amount_without_date_fails(self):
        template = MappingTemplate.objects.create(name="x", source_id="x", default_currency="INR")
        ColumnMapping.objects.create(template=template, source_header="id", role="external_ref")
        ColumnMapping.objects.create(template=template, source_header="amt", role="amount")
        with self.assertRaises(ValueError) as ctx:
            validate_template(template)
        self.assertIn("transaction date", str(ctx.exception).lower())

    def test_ymd_only_passes(self):
        template = MappingTemplate.objects.create(name="y", source_id="y", default_currency="INR")
        ColumnMapping.objects.create(template=template, source_header="id", role="external_ref")
        ColumnMapping.objects.create(template=template, source_header="amt", role="amount")
        ColumnMapping.objects.create(template=template, source_header="Y", role="date_year")
        ColumnMapping.objects.create(template=template, source_header="M", role="date_month")
        ColumnMapping.objects.create(template=template, source_header="D", role="date_day")
        validate_template(template)


class PiiHelperTests(TestCase):
    def test_encrypt_is_not_plaintext(self):
        token = encrypt_pii("4111111111111111")
        self.assertNotEqual(token, "4111111111111111")
        self.assertGreater(len(token), 20)
