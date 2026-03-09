# scripts

Runnable admin/ops scripts (e.g. one-off ingest), not part of the agent runtime.

- **upsert_rag_docs.py** – Upsert PDFs to Pinecone (delegates to `src.ingest`).  
  Prefer: `python -m src.ingest.run_upsert [folder] [namespace]` from project root.
