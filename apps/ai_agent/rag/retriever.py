"""
CONCEPT TO LEARN: RAG, using pgvector (so you don't need a separate vector DB —
your Postgres already holds the data).

Knowledge base to embed later: past resolved exceptions + their resolution
notes, and your written reconciliation rules/policies. When a NEW exception
comes in, retrieve the most similar past cases as context.

TODO (together, once we get here):
1. Add pgvector extension + an embedding column to a KnowledgeChunk model
2. embed_text(text) -> vector, using an embeddings model
3. retrieve(query_text, k=5) -> top-k similar KnowledgeChunks via cosine distance
"""
