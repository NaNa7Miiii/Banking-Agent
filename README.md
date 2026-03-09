# Refactored – Planner (Step 1)

Independent of `src/`. Contains planner and prompt assets only; no subagent execution.

## Layout

- **prompts/** – Versioned prompt assets (see `prompts/README.md`).
  - `planner/system.md`, `planner/meta.yaml`, `planner/output_schema.json`
- **utils/** – Shared helpers: `env` (load .env from project root), `prompt_loader` (load .md/meta).
- **models/llm.py** – Standalone OpenAI LLM; no dependency on src.
- **graph/** – `state.py`, `planner.py`, `main_graph.py` (planner-only graph).
- **run.py** – CLI entrypoint; when run from command line, prints the generated plan.

## Run (from project root)

```bash
# Ensure OPENAI_API_KEY is set (e.g. in .env at project root)
python -m refactored.run "How much did I spend this month?"
python -m refactored.run "用户输入" [customer_id] [session_id]
```

The planner output (JSON plan) is printed to stdout.

## Dependencies

- Project root `.env` for `OPENAI_API_KEY`.
- Python deps: `openai`, `langgraph`, `python-dotenv`, `jsonschema` (for validating planner output against `output_schema.json`). Optional: `pyyaml` for full `meta.yaml` parsing in `prompt_loader`.
