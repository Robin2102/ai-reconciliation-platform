"""Load-test ops (ingestion jobs require staff login — use Django test suite for ingest throughput).

    locust -f locustfile.py --host http://127.0.0.1:8000
"""

from locust import HttpUser, between, task


class OpsHealthUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def ops_login_page(self):
        self.client.get("/ops/login/", name="/ops/login/")
