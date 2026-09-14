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

Ingest is asynchronous: HTTP saves the file and enqueues a Celery task;
`RawRecord` + `Transaction` rows appear when the worker finishes. Matching,
exceptions, Kafka, and the agent are scaffolded but not wired to the API.

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
| Adaptors | Hide source format. `CsvAdapter` is registered as `source_type=csv`. |
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
| `source_type` | no | Default `csv` |
| `source_id` | no | Defaults to the filename stem |

```bash
curl -sS -F "file=@./sample.csv" -F "source_type=csv" -F "source_id=hdfc-sep" \
  http://127.0.0.1:8000/api/ingest/
```

**202** with `task_id`, `status: queued`, `source_type`, `source_id`. Rows are
not in the database until the worker runs `ingest_source`. Unknown
`source_type` or an empty file returns **400** and does not enqueue.
Admin upload (`/admin/ingestion/rawrecord/upload/`) uses the same queue.

`GET /admin/` — Django admin.  
`GET /silk/` — request/SQL profiler when `django-silk` is installed and `DEBUG` is true.

## Data

- **`RawRecord`** — untouched row JSON, `source_type`, `source_id`, ingest status.
- **`Transaction`** — canonical credit/debit, signed `amount`, currency, timestamp, `external_ref`.
- In-memory contract is Pydantic `CanonicalRecord` (`apps.adaptors.base`).

## Tests

```bash
python manage.py test apps.adaptors apps.ingestion
```
