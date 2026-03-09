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
├── src/                      # Main package
│   ├── graph/                # LangGraph components
│   │   ├── planner/          # Plan generation (goal + steps)
│   │   ├── executor/        # Step router & execution (SQL/RAG/Fraud)
│   │   ├── orchestrator/    # Loop: execute → merge → aggregate (and replan)
│   │   ├── nodes/           # Runtime graph nodes
│   │   ├── sql_agent/
│   │   ├── rag_agent/
│   │   ├── fraud_agent/
│   │   ├── main_graph.py
│   │   └── runtime_graph.py
│   ├── prompts/             # Versioned prompt assets
│   ├── ingest/               # RAG ingest (PDF → Pinecone)
│   ├── scripts/
│   ├── utils/                # env, db, memory, prompt_loader
│   ├── models/               # LLM (OpenAI)
│   └── run.py                # CLI entrypoint
├── .gitignore
├── README.md
└── requirements.txt
```

## Run (from repo root)

```bash
# Set OPENAI_API_KEY (e.g. in .env at repo root)
python -m src.run "How much did I spend this month?"
python -m src.run "用户输入" [customer_id] [session_id]
```

**Graph-native orchestration**: `USE_RUNTIME_GRAPH=1 python -m src.run "your question" [customer_id] [session_id]`

**Plan only**: `from src.run import run_planner` → `run_planner("...")` returns `result["plan"]`.

## Dependencies

- Repo root `.env` (OPENAI_API_KEY; optional DB_*, Redis, Pinecone, Tavily).
- Python: see `requirements.txt`.
