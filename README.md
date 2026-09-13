# Django (DRF) Monolith — AI-Powered Reconciliation Platform

One deployable Django project. Apps are internal modules, not separate services —
this mirrors the production pattern you already know (Bancapp), which is exactly
why we start here: you get to learn the NEW concepts (Kafka, RAG, Agents) without
also fighting an unfamiliar framework at the same time.

## Suggested learning order (do NOT jump ahead — each concept builds on the last)
1. `apps/adaptors/` — Adapter + Factory pattern (portable data source adaptors)
2. `apps/ingestion/` — Celery tasks + Kafka producer (raw data -> event stream)
3. `apps/reconciliation/` — Strategy pattern for matching rules (exact/fuzzy/AI)
4. `apps/exceptions/` — what happens when reconciliation can't auto-match
5. `apps/ai_agent/` — RAG (retrieval) then Agents (tool-using investigator)

See `/ARCHITECTURE.md` at the repo root for the full system design and the
monolith-vs-microservice discussion.
