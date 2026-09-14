# Reconciliation platform (Django / DRF)

Django monolith that ingests ledger files, normalizes them to a canonical
transaction shape, and will match, exception-manage, and investigate mismatches
in the same codebase. Apps are Python modules in one deployable unit: one
database, one settings module, web plus optional Celery workers.

Repo-level design (including the FastAPI service split): [`../ARCHITECTURE.md`](../ARCHITECTURE.md).
What was built in each phase: [`../PHASES.md`](../PHASES.md).

## Architecture

```
CSV / other sources
        │
        ▼
  Mapping studio (`/ops/`)               template: roles, date format, PII, default CCY
        │
        ▼
  Data adaptors                 one CanonicalRecord contract per row
        │
        ▼
  Ingestion                     RawRecord (audit) + Transaction (matchable)
        │
        ▼
  Reconciliation engine         exact / fuzzy / embedding strategies
        │
   matched ──► Transaction pair
        │
   unmatched ──► Exception queue ──► RAG + investigator agent ──► human review
```

Ingest is asynchronous: HTTP API saves the file and enqueues a Celery task;
`RawRecord` + `Transaction` rows appear when the worker finishes. Operators
use **`/ops/`** (staff login) to stage a file, map columns, then **Run ingest**.
`/admin/` is CRUD/inspection only. Matching, exceptions, and the agent are
not wired yet.

```
django-monolith/
├── config/                 Django settings, URLs, Celery app
├── apps/adaptors/          Source adapters → CanonicalRecord
├── apps/ingestion/         Staging store + ingest HTTP API
├── apps/reconciliation/    Canonical Transaction + match engine
├── apps/exceptions/        Unmatched-item lifecycle
└── apps/ai_agent/          Retrieval + tool-using investigator
```

| Layer | Responsibility |
| --- | --- |
| Adaptors | Hide source format. `csv` and `txt` adapters share delimited extract (comma/semicolon/tab/pipe). |
| Ingestion | Persist raw payloads, then validated canonical rows. |
| Reconciliation | Store `Transaction`; matching strategies live under `engine/`. |
| Infra | Postgres or SQLite; Redis (Celery); Compose Kafka + Kafka UI. |

Web and workers must use the same database. From the host machine, compose
services are `localhost`. From another container, use hostnames `postgres`,
`redis`, `kafka`.

## Configuration

Copy `env.example` to `.env` (gitignored). `config/settings.py` loads `.env`.

| Variable | Purpose |
| --- | --- |
| `USE_SQLITE` | `1` (default) = file SQLite. `0` = Postgres from the vars below. |
| `POSTGRES_*` | DB name, user, password, host, port. Compose publishes Postgres on **5433**. |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Redis, default `redis://localhost:6379/0`. |
| `KAFKA_BOOTSTRAP_SERVERS` | Compose Kafka, `127.0.0.1:9092`. |
| `SECRET_KEY` / `DEBUG` / `ALLOWED_HOSTS` | Required in `.env`. Never commit `SECRET_KEY`. |

`manage.py test` always uses SQLite, regardless of `USE_SQLITE`.

## Run

```bash
cd django-monolith
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env
```

SQLite:

```bash
python manage.py migrate
python manage.py runserver
```

Postgres (from repo root):

```bash
docker compose up -d postgres
```

Set `USE_SQLITE=0` in `.env`, then `migrate` and `runserver` in this directory.

Redis (required for ingest) from the repo root:

```bash
docker compose up -d redis
```

Two processes — API and worker:

```bash
python manage.py runserver
# other terminal, same venv, django-monolith/
celery -A config worker --loglevel=info
```

Without a worker, Redis queues messages and nothing is ingested.

Kafka (Compose, same topology you would ship: broker + UI):

```bash
# stop Confluent Local if it is still running, so you only have one cluster
confluent local kafka stop

docker compose up -d kafka kafka-ui
```

`.env` must be `KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:9092`. Restart the Celery worker. Then:

```bash
python manage.py consume_ingestion_events
```

Inspect topics at `http://localhost:8080`. The app talks to **one** bootstrap; running Confluent Local at the same time is a second cluster and is ignored unless you change that env var.

## HTTP API

`POST /api/ingest/` — multipart upload.

| Field | Required | Notes |
| --- | --- | --- |
| `file` | yes | CSV bytes |
| `source_type` | no | `csv` (default) or `txt` |
| `source_id` | no | Defaults to the filename stem |

```bash
curl -sS -F "file=@./sample.csv" -F "source_type=csv" -F "source_id=hdfc-sep" \
  http://127.0.0.1:8000/api/ingest/
```

**202** with `task_id`, `status: queued`, `source_type`, `source_id`. Rows are
not in the database until the worker runs `ingest_source` with the CSV adapter
heuristics (no mapping template). Unknown `source_type` or an empty file
returns **400** and does not enqueue.

Ops UI (`/ops/`) — staff login. Upload stages an `IngestFile`; mapping studio
profiles columns. Save a template, then **Run ingest** (Celery + Kafka after
commit). Set `PII_FERNET_KEY` in `.env` (see `env.example`).

`GET /admin/` — Django admin (inspect RawRecord / Transaction / templates).  
`GET /silk/` — request/SQL profiler when `django-silk` is installed and `DEBUG` is true.

## Data

- **`IngestFile`** — staged upload before mapping/ingest.
- **`MappingTemplate` / `ColumnMapping`** — reusable column roles for a `source_id`.
- **`RawRecord`** — row JSON (PII columns encrypted when tagged), `source_type`, `source_id`, ingest status.
- **`Transaction`** — canonical credit/debit, signed `amount`, currency, `timestamp` (transaction datetime), `external_ref` (reference / match key from mapped **Reference** columns).
- Each row’s `raw_payload._generated` includes `transaction_date` (date-only copy of the mapped transaction date), `uploaded_date`, `txn_type`, and `reconciled_date` / `reconciled_by` (null until matching or exception closure).
- In-memory contract is Pydantic `CanonicalRecord` (`apps.adaptors.base`).

## Tests

```bash
python manage.py test apps.adaptors apps.ingestion
```
