# Banking Agent (Reorg)

Agentic workflow for banking operations, built with LangGraph. A single runtime graph runs the **planner**, **orchestrator**, and **subagents** (SQL, RAG, Fraud) from user input to final answer, with Redis-backed conversation memory.

## Features

- **Planner** – Turns user questions into a structured multi-step plan (goal, steps with owner and dependencies).
- **Runtime graph** – One graph: planner → init → select → execute (concurrent waves) → merge → evaluate → aggregate; replan on failure when needed.
- **SQL Agent** – Read-only queries with pairwise candidate selection and safe execution layer.
- **RAG Agent** – Vector search (Pinecone) and Tavily web search (gated for public/policy queries only).
- **Fraud Agent** – ML-based transaction fraud/risk scoring.
- **Conversation memory** – Redis-backed history for multi-turn context.

## Prerequisites

- Python 3.10+
- Docker (for Redis)
- PostgreSQL (transaction DB)
- API keys: OpenAI, Pinecone, Tavily

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/NaNa7Miiii/Banking_Agent.git
   cd Banking_Agent/Banking_Agent_reorg
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Setting Up Redis with Docker

Redis backs conversation memory for multi-turn context.

### Using Docker to Run Redis

1. **Pull and run Redis container**
   ```bash
   docker run -d \
     --name redis-banking-agent \
     -p 6379:6379 \
     redis:latest
   ```

2. **Verify Redis is running**
   ```bash
   docker ps
   ```

3. **Test connection**
   ```bash
   docker exec -it redis-banking-agent redis-cli ping
   # Should return: PONG
   ```

### Redis Management Commands

- **Stop**: `docker stop redis-banking-agent`
- **Start**: `docker start redis-banking-agent`
- **Remove**: `docker stop redis-banking-agent && docker rm redis-banking-agent`

### Redis Configuration

Defaults are in `src/utils/memory.py` (e.g. `localhost:6379`). Override via env or edit that file if needed.

## Environment Configuration

Create a `.env` file at the **project root** (e.g. `Banking_Agent_reorg/.env`):

```env
OPENAI_API_KEY=your-openai-api-key

DB_HOST=your-database-host
DB_PASSWORD=your-database-password
DB_USERNAME=postgres
DB_PORT=5432
DB_DATABASE=customer_transaction_db
DB_TABLE_NAME=transactions

PINECONE_API_KEY=your-pinecone-api-key
TAVILY_SEARCH_KEY=your-tavily-api-key

REDIS_HOST=localhost
REDIS_PORT=6379
```

## Usage

### Run from project root

Run from the **repository root** so that `python -m src.run` resolves (e.g. from `Banking_Agent_reorg` if that is your working directory):

```bash
# From Banking_Agent_reorg/
python -m src.run "How much did I spend this month?"
python -m src.run "What is the overdraft policy?" [customer_id] [session_id]
```

With `customer_id` and `session_id`, conversation memory is used.

### Using as a Python module

```python
from src.run import run_task

result = run_task(
    user_input="How much did I spend this month?",
    customer_id_number="12345",
    session_id="session-abc",
)

print(result["plan"])
print(result["final_answer"])
print(result["execution_state"])
```

## Project Structure

```
Banking_Agent_reorg/
├── src/
│   ├── graph/
│   │   ├── planner/           # Plan generation (goal + steps)
│   │   ├── executor/          # Step router & execution (SQL/RAG/Fraud)
│   │   ├── orchestrator/      # Aggregation helpers
│   │   ├── nodes/             # Runtime graph nodes (init, select, execute, merge, evaluate, aggregate)
│   │   ├── sql_agent/
│   │   ├── rag_agent/
│   │   ├── fraud_agent/
│   │   ├── runtime_state.py
│   │   └── runtime_graph.py   # Single full graph
│   ├── prompts/               # Versioned prompt assets
│   ├── ingest/                # RAG ingest (PDF → Pinecone)
│   ├── scripts/
│   ├── utils/                 # env, db, memory, prompt_loader
│   ├── models/                # LLM (OpenAI)
│   └── run.py                 # CLI entrypoint
├── .gitignore
├── README.md
└── requirements.txt
```

The top-level package is `src`. Always run from the project root so `python -m src.run` works.

## Runtime Flow

1. **Planner** – LLM produces a JSON plan (goal, steps, dependencies, join points).
2. **Init** – Prepares orchestration state and parallel groups.
3. **Select** – Picks ready steps (dependencies satisfied).
4. **Execute** – Runs each wave (single or parallel group) via subagents (SQL / RAG / Fraud).
5. **Merge** – Combines results after a parallel group when all steps in the group succeed.
6. **Evaluate** – Decides whether to aggregate or replan.
7. **Aggregate** – Builds the final answer from step results.
