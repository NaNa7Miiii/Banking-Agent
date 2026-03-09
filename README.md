# Banking Agent (refactored)

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
│   ├── executor/             # Step router & execution (SQL/RAG/Fraud)
│   ├── orchestrator/         # Loop: execute → merge → aggregate (and replan)
│   ├── nodes/                # Runtime graph nodes (init, select, execute, merge, evaluate, replan, aggregate)
│   ├── sql_agent/            # SQL tools + ReAct agent
│   ├── rag_agent/            # RAG + Tavily tools + ReAct agent
│   ├── fraud_agent/          # Fraud tools + batch inference + ReAct agent
│   ├── main_graph.py         # Plan-only graph
│   ├── runtime_graph.py      # Full graph-native orchestration (concurrent steps, replan)
│   └── runtime_state.py      # State for runtime graph
├── prompts/                  # Versioned prompt assets (.md + meta.yaml)
│   ├── planner/
│   ├── aggregation/
│   ├── sql_agent/
│   ├── rag_agent/
│   └── fraud_agent/
├── ingest/                   # RAG ingest (PDF → split → upsert to Pinecone)
├── scripts/
├── utils/                    # env, db, memory, prompt_loader
├── models/                   # LLM (OpenAI)
├── run.py                    # CLI entrypoint
└── (see project root requirements.txt)
```

## Run (from project root)

```bash
python -m refactored.run "How much did I spend this month?"
python -m refactored.run "用户输入" [customer_id] [session_id]
```

**Graph-native orchestration**: `USE_RUNTIME_GRAPH=1 python -m refactored.run "your question" [customer_id] [session_id]`

**Plan only**: `from refactored.run import run_planner` → `run_planner("...")` returns `result["plan"]`.

## Dependencies

- Project root `.env` (OPENAI_API_KEY; optional DB_*, Redis, Pinecone, Tavily).
- Python: openai, langgraph, python-dotenv, jsonschema, pyyaml; see root `requirements.txt`.
