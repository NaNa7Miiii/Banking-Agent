# Banking Agent

Agentic workflow with **planner**, **orchestrator**, **SQL**, **RAG** (vector DB + web search), and **transaction fraud detection** agents. Built with LangGraph.

## Features

- **Planner** – Turns user questions into a structured multi-step plan (goal + steps with owner/tool).
- **Orchestrator** – Runs plan steps (sequential or graph-native concurrent), merges results, optional replan.
- **SQL Agent** – Read-only queries on the transaction database.
- **RAG Agent** – Vector search (Pinecone) + optional Tavily web search.
- **Fraud Agent** – ML-based transaction fraud/risk scoring.
- **Conversation memory** – Redis-backed history (optional) for multi-turn context.

## Layout

```
├── graph/                    # LangGraph components
│   ├── planner/              # Plan generation (goal + steps)
│   ├── executor/              # Step router & execution (SQL/RAG/Fraud)
│   ├── orchestrator/         # Loop: execute → merge → aggregate (and replan)
│   ├── nodes/                # Runtime graph nodes (init, select, execute, merge, evaluate, replan, aggregate)
│   ├── sql_agent/            # SQL tools + ReAct agent
│   ├── rag_agent/            # RAG + Tavily tools + ReAct agent
│   ├── fraud_agent/          # Fraud tools + batch inference + ReAct agent
│   ├── main_graph.py         # Plan-only graph
│   ├── runtime_graph.py      # Full graph-native orchestration (concurrent steps, replan)
│   └── runtime_state.py      # State for runtime graph
├── prompts/                  # Versioned prompt assets (.md + meta.yaml)
│   ├── planner/              # Planner system prompt, output schema
│   ├── aggregation/         # Final answer aggregation
│   ├── sql_agent/
│   ├── rag_agent/
│   └── fraud_agent/
├── ingest/                   # RAG ingest (PDF → split → upsert to Pinecone)
├── scripts/                  # Index creation, RAG upsert helpers
├── utils/                    # env, db, memory, prompt_loader
├── models/                   # LLM (OpenAI)
├── resources/                # Optional static/resources
├── run.py                    # CLI entrypoint
└── requirements.txt
```

## Run

The code is intended to be run as the **`refactored`** package (e.g. this repo lives as `refactored/` inside a project). From the **project root** (parent of `refactored/`):

```bash
# Set OPENAI_API_KEY (e.g. in .env at project root)
python -m refactored.run "How much did I spend this month?"
python -m refactored.run "用户输入" [customer_id] [session_id]
```

- With `customer_id` and `session_id`: conversation memory is loaded/saved (Redis).
- **Full execution**: planner runs, then each plan step is executed (SQL/RAG/Fraud), results are merged and aggregated into a final answer.

**Graph-native orchestration** (concurrent step execution + replan on failure):

```bash
USE_RUNTIME_GRAPH=1 python -m refactored.run "your question" [customer_id] [session_id]
```

**Plan only** (no step execution):

```python
from refactored.run import run_planner
result = run_planner("How much did I spend?")
print(result["plan"])
```

## Dependencies

- **Environment**: `.env` at project root with at least `OPENAI_API_KEY`. Optional: DB_*, Redis, Pinecone, Tavily (see `utils/env.py`).
- **Python**: `requirements.txt` (openai, langgraph, python-dotenv, jsonschema, pyyaml; DB/Redis/Pinecone/Tavily as needed).

## Optional

- **RAG ingest**: run ingest from project root so `refactored` is importable: `python -m refactored.ingest.run_upsert <path_to_pdfs>` (or use `scripts/upsert_rag_docs.py`).
- **Redis**: for conversation memory; configure in `utils/memory.py`.
