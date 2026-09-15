# Phase 7 — RAG (follow these steps)

RAG here = **retrieve similar resolved exceptions** before any LLM (Phase 8). No chatbot yet.

## What was added

| Piece | Location |
|-------|----------|
| `KnowledgeChunk` model | `apps/ai_agent/models.py` |
| Embeddings | `apps/ai_agent/rag/embeddings.py` (`fake` default, optional `sentence_transformers`) |
| Index from exceptions | `apps/ai_agent/rag/indexing.py` |
| Retrieve top-k | `apps/ai_agent/rag/retriever.py` |
| Tool for agents | `apps/ai_agent/tools/tools.py` → `retrieve_similar_past_cases()` |
| Bulk index command | `python manage.py index_exception_knowledge` |
| Ops UI | Exception detail → **Similar past cases (RAG)** |
| Auto-index | When you resolve / reject / write-off in ops |

---

## Step 1 — Migrate

```bash
cd django-monolith
source .venv/bin/activate
python manage.py migrate
```

---

## Step 2 — Seed knowledge (your data)

**Option A — resolve in UI (auto-index)**  
1. Reconciliation → project → **Exceptions**  
2. Open an exception → **Write-off** or **Manual match** with a **note**  
   e.g. `Extract INV-1001 from bank narration; matched to ledger reference.`  
3. Repeat for 2–3 similar cases.

**Option B — backfill existing resolved rows**

```bash
python manage.py index_exception_knowledge
```

---

## Step 3 — See retrieval

1. Open another **open** exception (same project).  
2. Scroll to **Similar past cases (RAG)** — top notes ranked by embedding similarity.

Use demo files in [`../samples/rag-recon/`](../samples/rag-recon/) if you need quick exceptions.

---

## Step 4 — (Optional) Better embeddings

Default `RAG_EMBEDDING_BACKEND=fake` works offline (deterministic, good for learning).

For stronger similarity on real text, in `.env`:

```env
RAG_EMBEDDING_BACKEND=sentence_transformers
```

Then install once:

```bash
pip install sentence-transformers
```

Re-index everything (vectors must use the same backend):

```bash
python manage.py index_exception_knowledge
```

---

## Step 5 — Inspect in admin

`/admin/` → **Knowledge chunks** — see `text` + metadata (no raw PII payloads).

---

## Step 6 — Next (Phase 8)

- Investigator agent calls `retrieve_similar_past_cases()` then drafts `ai_suggestion`  
- Still **human approves** — no auto-post

---

## Mental model (interview)

1. **Matcher** = deterministic rules.  
2. **Exception** = queue + resolution notes.  
3. **RAG** = embed notes + refs → cosine search on new case.  
4. **LLM** (later) only reads retrieved chunks, not the whole DB.
