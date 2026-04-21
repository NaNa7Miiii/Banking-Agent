"""
Fraud agent pipeline.

Public surface:
    * ``invoke(req: FraudAgentRequest) -> FraudAgentResponse`` — typed contract.
    * ``run_fraud_agent(...)`` — legacy dict shape, kept for internal callers.
"""
from typing import Any, List, Optional

from src.graph.fraud_agent.agent import run_fraud_agent_react
from src.graph.fraud_agent.schema import FraudAgentRequest, FraudAgentResponse
from src.utils.json_safe import to_json_safe


def run_fraud_agent(
    question: str,
    current_user_id: str,
    initial_sql_result: Optional[List[Any]] = None,
    initial_sql_answer: Optional[str] = None,
) -> dict[str, Any]:
    """Legacy dict-shaped entry point."""
    return run_fraud_agent_react(
        question=question,
        current_user_id=current_user_id,
        initial_sql_result=initial_sql_result,
        initial_sql_answer=initial_sql_answer,
    )


def invoke(req: FraudAgentRequest) -> FraudAgentResponse:
    """Typed entry point."""
    try:
        raw = run_fraud_agent(
            question=req.instruction,
            current_user_id=req.current_user_id,
            initial_sql_result=req.initial_sql_result,
            initial_sql_answer=req.initial_sql_answer,
        )
    except Exception as exc:
        return FraudAgentResponse(status="error", error=str(exc))

    error = raw.get("error")
    status = "error" if error else "ok"
    return FraudAgentResponse(
        status=status,
        summary=(raw.get("analysis") or "").strip() if status == "ok" else "",
        risk_scores=to_json_safe(raw.get("risk_scores")),
        profile=to_json_safe(raw.get("profile")),
        error=error,
    )
