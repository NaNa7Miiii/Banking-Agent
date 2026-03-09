"""
Unified executor: execute_step(step, context) -> StepResult.
Consumes step["instruction"] only; enforces non-empty instruction; routes via router registry (canonical owner).
"""
import time
from typing import Any

from refactored.graph.executor.schema import StepResult, ExecutionContext
from refactored.graph.executor.router import get_canonical, register, ROUTER, supported_owners


def _instruction_from_step(step: dict[str, Any]) -> str:
    """Contract: planner must output instruction; planner node sets instruction from title if missing."""
    return (step.get("instruction") or "").strip()


def _build_result(
    step: dict[str, Any],
    status: str,
    summary: str,
    artifacts: dict[str, Any],
    error_message: str = "",
    agent_name: str | None = None,
) -> StepResult:
    """Single place to build StepResult. step must have id and owner (use normalized step from execute_step)."""
    step_id = step.get("id", "")
    owner = step.get("owner", "")
    return {
        "step_id": step_id,
        "owner": owner,
        "status": status,
        "data": {
            "summary": summary if status == "ok" else "",
            "artifacts": artifacts,
        },
        "error_message": error_message,
        "metadata": {
            "agent": agent_name,
            "owner": owner,
            "timestamp": time.time(),
        },
    }


def _run_sql(step: dict[str, Any], context: ExecutionContext) -> StepResult:
    from refactored.graph.sql_agent.pipeline import run_sql_agent
    instruction = _instruction_from_step(step)
    user_id = context.get("current_user_id") or ""
    out = run_sql_agent(question=instruction, current_user_id=user_id)
    status = "ok" if not out.get("error") else "error"
    summary = (out.get("answer") or "").strip() if status == "ok" else ""
    return _build_result(
        step, status, summary,
        artifacts={"sql": out.get("sql"), "result": out.get("result")},
        error_message=(out.get("error") or "") if status == "error" else "",
        agent_name="sql_agent",
    )


def _run_rag(step: dict[str, Any], context: ExecutionContext) -> StepResult:
    from refactored.graph.rag_agent.pipeline import run_rag_agent
    instruction = _instruction_from_step(step)
    ns = context.get("namespace")
    out = run_rag_agent(question=instruction, namespace=ns)
    status = "ok" if not out.get("error") else "error"
    summary = (out.get("answer") or "").strip() if status == "ok" else ""
    return _build_result(
        step, status, summary,
        artifacts={
            "citations": out.get("citations", []),
            "route_decision": out.get("route_decision"),
        },
        error_message=(out.get("error") or "") if status == "error" else "",
        agent_name="rag_agent",
    )


def _run_fraud(step: dict[str, Any], context: ExecutionContext) -> StepResult:
    from refactored.graph.fraud_agent.pipeline import run_fraud_agent
    instruction = _instruction_from_step(step)
    user_id = context.get("current_user_id") or ""
    prev_results = context.get("previous_step_results") or {}
    initial_sql_result = None
    initial_sql_answer = None
    for dep in (step.get("depends_on") or []):
        dep_id = (dep.get("step_id") or "").strip()
        if not dep_id:
            continue
        sr = prev_results.get(dep_id) or {}
        if sr.get("status") != "ok":
            continue
        data = sr.get("data") or {}
        artifacts = data.get("artifacts") or {}
        if "result" in artifacts and artifacts["result"] is not None:
            initial_sql_result = artifacts["result"]
            initial_sql_answer = (data.get("summary") or "").strip()
            break
    question = instruction
    if initial_sql_result is not None:
        question = f"{instruction}\n\n(Transaction data from the previous step is already loaded; call analyze_risk_scores_batch with input 'use last result' to score it.)"
    out = run_fraud_agent(
        question=question,
        current_user_id=user_id,
        initial_sql_result=initial_sql_result,
        initial_sql_answer=initial_sql_answer,
    )
    status = "ok" if not out.get("error") else "error"
    summary = (out.get("analysis") or "").strip() if status == "ok" else ""
    return _build_result(
        step, status, summary,
        artifacts={"risk_scores": out.get("risk_scores"), "profile": out.get("profile")},
        error_message=(out.get("error") or "") if status == "error" else "",
        agent_name="fraud_agent",
    )


# Register only canonical owners so trace/aggregation see one format.
register("subagent:sql", _run_sql)
register("subagent:rag", _run_rag)
register("subagent:fraud", _run_fraud)

# For exception branch: canonical agent name from handler (for metadata consistency).
_HANDLER_AGENT_NAME: dict[Any, str] = {
    _run_sql: "sql_agent",
    _run_rag: "rag_agent",
    _run_fraud: "fraud_agent",
}


def execute_step(step: dict[str, Any], context: ExecutionContext) -> StepResult:
    """
    Execute one plan step. Requires non-empty step["instruction"]; canonicalizes owner; routes via ROUTER.
    Writes normalized id/owner back into a step copy so handlers see canonical owner and consistent step_id.
    """
    step_id = step.get("id") or ""
    owner_raw = (step.get("owner") or "").strip()
    owner_canonical = get_canonical(owner_raw)

    # Single normalized step: handlers and all _build_result calls use this (canonical owner, stable id).
    step_normalized = dict(step)
    step_normalized["id"] = step_id
    step_normalized["owner"] = owner_canonical or owner_raw

    instruction = _instruction_from_step(step)
    if not instruction:
        return _build_result(
            step_normalized,
            status="error",
            summary="",
            artifacts={},
            error_message="Missing step instruction",
            agent_name=None,
        )

    handler = ROUTER.get(owner_canonical)
    if handler is None:
        return _build_result(
            step_normalized,
            status="error",
            summary="",
            artifacts={},
            error_message=f"Unknown owner: {owner_canonical or owner_raw}. Supported: {supported_owners()}",
            agent_name=None,
        )

    try:
        return handler(step_normalized, context)
    except Exception as e:
        agent_name = _HANDLER_AGENT_NAME.get(handler)
        return _build_result(
            step_normalized,
            status="error",
            summary="",
            artifacts={},
            error_message=str(e),
            agent_name=agent_name,
        )
