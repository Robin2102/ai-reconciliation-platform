"""
CONCEPT TO LEARN: Agentic AI — the "Exception Investigator" agent.

Given one open ExceptionRecord, this agent should be able to:
1. Reason about what's missing (thought)
2. Call TOOLS to gather more info: query_upstream_source(), run_fuzzy_match(),
   retrieve_similar_past_cases() [the RAG retriever above]
3. Decide: auto-resolve (high confidence) or draft a note for a human (low confidence)

This is the ReAct loop from your interview prep, made concrete.
TODO (together, after RAG + tools exist): build the loop step by step, don't
skip to a framework (LangGraph etc.) until you've built one by hand once.
"""
