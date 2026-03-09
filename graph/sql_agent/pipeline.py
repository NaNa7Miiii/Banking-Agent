"""
SQL agent: LangChain create_agent with tools (get_schema, get_value_constraints, propose_sql, execute_sql, fix_sql).
"""
from typing import Any

from refactored.graph.sql_agent.agent import run_sql_agent_react


def run_sql_agent(
    question: str,
    current_user_id: str,
    max_fix_attempts: int = 2,
) -> dict[str, Any]:
    """
    Run the SQL agent (LangChain create_agent) and return:
    answer, sql, result, error.
    max_fix_attempts is kept for backward compatibility; the agent decides fix/execute loops via the prompt.
    """
    return run_sql_agent_react(question=question, current_user_id=current_user_id)
