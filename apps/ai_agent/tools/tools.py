"""
CONCEPT TO LEARN: what a 'tool' actually is — just a plain Python function
with a clear docstring/schema, that the agent is ALLOWED to call.

TODO (together): query_upstream_source(source_id), run_fuzzy_match(a, b)
[reuses FuzzyMatchStrategy], retrieve_similar_past_cases(text) [reuses the
RAG retriever]. Each should be small, testable, and callable outside the
agent too — the agent is just a decision-maker on top of tools you already trust.
"""
