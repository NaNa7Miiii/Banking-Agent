"""
SQL agent tools for LangChain create_agent: factory returning tools bound to engine, user, question, and a collector.
"""
import json
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.engine import Engine

from src.graph.sql_agent.config import USER_COLUMN, FORBIDDEN_COLUMNS, get_max_sql_rows
from src.graph.sql_agent.utils.schema import get_schema as fetch_schema
from src.graph.sql_agent.utils.value_retrieval import (
    get_candidate_filter_values,
    get_date_range_for_user,
)
from src.graph.sql_agent.utils.generators import (
    generate_direct_candidates,
    generate_dc_candidate,
)
from src.graph.sql_agent.utils.execution import execute_read_only_sql
from src.graph.sql_agent.utils.fixer import query_fixer
from src.graph.sql_agent.selection import pairwise_select


def _gather_value_retrieval(
    engine: Engine,
    table_name: str,
    question: str,
    current_user_id: str,
) -> dict[str, Any]:
    values = get_candidate_filter_values(
        engine, table_name, question, current_user_id, USER_COLUMN
    )
    date_range = get_date_range_for_user(
        engine, table_name, current_user_id, USER_COLUMN
    )
    for k, v in date_range.items():
        values[k] = v
    return values


def make_sql_tools(
    engine: Engine,
    table_name: str,
    current_user_id: str,
    question: str,
) -> tuple[list, dict[str, Any]]:
    """
    Returns (list of LangChain tools, collector dict).
    Collector holds: schema, value_retrieval, sql, result, error.
    """
    collector: dict[str, Any] = {
        "schema": "",
        "value_retrieval": {},
        "sql": None,
        "result": None,
        "error": None,
    }

    @tool
    def get_schema() -> str:
        """Get the table schema (columns and types). Call this first."""
        schema = fetch_schema(engine, table_name, FORBIDDEN_COLUMNS)
        collector["schema"] = schema
        return schema

    @tool
    def get_value_constraints() -> str:
        """Get available filter values and date range for the current user. Call after get_schema."""
        value_retrieval = _gather_value_retrieval(
            engine, table_name, question, current_user_id
        )
        collector["value_retrieval"] = value_retrieval
        value_retrieval_str: dict[str, Any] = {}
        for k, v in value_retrieval.items():
            if isinstance(v, list):
                value_retrieval_str[k] = v[:20]
            else:
                value_retrieval_str[k] = v
        summary = json.dumps(value_retrieval_str, ensure_ascii=False, default=str)
        return f"Value constraints and date range for user:\n{summary}"

    @tool
    def propose_sql() -> str:
        """Generate and select the best SQL query for the question. Call after get_schema and get_value_constraints."""
        schema = collector.get("schema") or fetch_schema(engine, table_name, FORBIDDEN_COLUMNS)
        if not schema:
            return "Error: schema not available. Call get_schema first."
        collector["schema"] = schema
        value_retrieval = collector.get("value_retrieval")
        if value_retrieval is None or value_retrieval == {}:
            value_retrieval = _gather_value_retrieval(
                engine, table_name, question, current_user_id
            )
            collector["value_retrieval"] = value_retrieval
        value_retrieval_str = {}
        for k, v in value_retrieval.items():
            if isinstance(v, list):
                value_retrieval_str[k] = v[:20]
            else:
                value_retrieval_str[k] = v

        candidates: list[str] = []
        try:
            candidates = generate_direct_candidates(
                schema, question, value_retrieval_str
            ) or []
        except Exception:
            pass
        try:
            dc_sql = generate_dc_candidate(schema, question, value_retrieval_str)
            if dc_sql and dc_sql not in candidates:
                candidates.append(dc_sql)
        except Exception:
            pass

        if not candidates:
            return "Could not generate any valid SQL for this question."

        winner_idx = pairwise_select(candidates, question, schema)
        chosen_sql = candidates[winner_idx]
        collector["sql"] = chosen_sql
        return f"Chosen SQL:\n{chosen_sql}"

    @tool
    def execute_sql(sql: str) -> str:
        """Run a read-only SQL query. Pass the exact SQL string. Returns result summary or error."""
        rows, err, truncated = execute_read_only_sql(
            engine, sql, current_user_id, USER_COLUMN, FORBIDDEN_COLUMNS
        )
        collector["sql"] = sql
        collector["result"] = rows
        collector["error"] = err
        cap = get_max_sql_rows()
        if truncated:
            collector["result_truncated_at"] = cap
        if err:
            return f"Error: {err}"
        if not rows:
            return "Success: 0 rows."
        result_str = json.dumps(rows[:30], ensure_ascii=False, default=str)
        msg = f"Success: {len(rows)} row(s). Sample:\n{result_str[:2000]}"
        if truncated:
            msg += f"\n(Results capped at {cap} rows. In your final answer, say the analysis is based on up to {cap} matching rows/transactions.)"
        return msg

    @tool
    def fix_sql(failed_sql: str, error_msg: str) -> str:
        """If execute_sql failed, pass the failed SQL and error message to get a corrected SQL."""
        schema = collector.get("schema") or fetch_schema(engine, table_name, FORBIDDEN_COLUMNS)
        fixed = query_fixer(question, schema, failed_sql, error_msg)
        if not fixed:
            return "Could not fix the SQL."
        return f"Corrected SQL:\n{fixed}"

    return [
        get_schema,
        get_value_constraints,
        propose_sql,
        execute_sql,
        fix_sql,
    ], collector
