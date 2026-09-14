# Tests

We use Django’s built-in test runner (`unittest` style). Each app keeps tests in a **`tests/` package** (not loose `test_*.py` at the app root).

## Layout

```
apps/<app>/tests/
  __init__.py
  fixtures.py / helpers.py   # optional shared CSV bodies, ingest helpers
  test_<area>.py             # one module per concern (api, ops, engine, …)
```

| App | Modules | What they cover |
| --- | --- | --- |
| `adaptors` | `test_adaptors.py` | CSV/TXT/XLSX/PDF extract + heuristic normalize |
| `ingestion` | `test_api.py`, `test_ops.py`, `test_services.py`, `test_mapping.py` | REST ingest, `/ops/` staging + mapping, Kafka hook, profiler/mapping |
| `reconciliation` | `test_engine_runs.py`, `test_engine_conditions.py`, `test_generated_fields.py` | Projects/runs, rule conditions, `_generated` fields |

Name files by **behavior** (`test_engine_runs`), not roadmap phase (`test_recon_5a`).

## Commands

```bash
cd django-monolith
source .venv/bin/activate

# Everything
python manage.py test

# One app (discovers apps.<app>.tests.test_*)
python manage.py test apps.ingestion
python manage.py test apps.reconciliation
python manage.py test apps.adaptors

# One module or class
python manage.py test apps.ingestion.tests.test_ops.IngestOpsTests
```

Tests always use **SQLite** (see `config/settings.py`), even when dev uses Postgres.

## Adding tests

1. Put new cases in the existing module for that layer, or add `test_<new_area>.py` under the app’s `tests/` package.
2. Reuse `apps/ingestion/tests/fixtures.py` or `apps/reconciliation/tests/helpers.py` instead of copying CSV strings.
3. Prefer small `TestCase` classes grouped by feature, not one giant file per app.

Cross-app integration tests can live under `apps/core/tests/` later if the monolith grows a dedicated `core` test home; for now, reconciliation tests import ingestion helpers where needed.
