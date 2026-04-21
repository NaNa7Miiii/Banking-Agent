"""
SQL agent: LangChain create_agent with tools
(get_schema, get_value_constraints, propose_sql, execute_sql, fix_sql).

Public surface:
    * ``invoke(req: SqlAgentRequest) -> SqlAgentResponse`` — typed, JSON-safe contract
      (the entry point the executor / FastAPI layer uses).
    * ``run_sql_agent(question, current_user_id, ...)`` — legacy dict-in/dict-out
      shape kept for internal callers (e.g. the fraud agent tools that already
      expect ``answer`` / ``sql`` / ``result`` keys).
"""
from typing import Any

from src.graph.sql_agent.agent import run_sql_agent_react
from src.graph.sql_agent.schema import SqlAgentRequest, SqlAgentResponse
from src.utils.json_safe import rows_to_json_safe


def run_sql_agent(
    question: str,
    current_user_id: str,
    max_fix_attempts: int = 2,
) -> dict[str, Any]:
    """Legacy dict-shaped entry point. Kept for internal callers."""
    return run_sql_agent_react(question=question, current_user_id=current_user_id)


def invoke(req: SqlAgentRequest) -> SqlAgentResponse:
    """Typed entry point: validated Pydantic in, JSON-safe Pydantic out."""
    try:
        raw = run_sql_agent_react(
            question=req.instruction,
            current_user_id=req.current_user_id,
        )
    except Exception as exc:  # defensive: never let the contract leak an exception
        return SqlAgentResponse(status="error", error=str(exc))

    error = raw.get("error")
    rows = rows_to_json_safe(raw.get("result"))
    status = "error" if error else "ok"
    return SqlAgentResponse(
        status=status,
        summary=(raw.get("answer") or "").strip() if status == "ok" else "",
        sql=raw.get("sql"),
        result=rows,
        row_count=len(rows) if rows is not None else None,
        error=error,
    )
