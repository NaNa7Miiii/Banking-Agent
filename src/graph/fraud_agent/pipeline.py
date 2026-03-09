"""
Fraud agent pipeline: single entry run_fraud_agent(question, current_user_id).
When previous_step_results provides SQL output (e.g. from graph step1), pass as initial_sql_* to skip re-fetch.
"""
from typing import Any, List, Optional

from src.graph.fraud_agent.agent import run_fraud_agent_react


def run_fraud_agent(
    question: str,
    current_user_id: str,
    initial_sql_result: Optional[List[Any]] = None,
    initial_sql_answer: Optional[str] = None,
) -> dict[str, Any]:
    """
    Run the fraud agent: fetch current user transactions via SQL agent (or use initial_sql_* if provided),
    batch score (CatBoost + IF), optionally query customer profile, then produce an interpretable risk analysis report.
    """
    return run_fraud_agent_react(
        question=question,
        current_user_id=current_user_id,
        initial_sql_result=initial_sql_result,
        initial_sql_answer=initial_sql_answer,
    )
