"""Load-test the ingest API.

Django must already be serving on :8000. Silk should be off or ignored for
throughput numbers — it records every request and inflates latency.

    locust -f locustfile.py --host http://127.0.0.1:8000
Then open http://localhost:8089
"""
from locust import HttpUser, between, task

CSV_BODY = (
    "txn_id,date,credit,debit,description,currency\n"
    "TXN-101,2026-09-12,1500.50,0.00,Salary,INR\n"
    "TXN-102,2026-09-12,0.00,200.00,Vendor,INR\n"
).encode("utf-8")


class IngestUser(HttpUser):
    wait_time = between(0.5, 1.5)

    @task
    def ingest_csv(self):
        self.client.post(
            "/api/ingest/",
            data={"source_type": "csv", "source_id": "locust-load"},
            files={"file": ("bank.csv", CSV_BODY, "text/csv")},
            name="/api/ingest/",
        )
