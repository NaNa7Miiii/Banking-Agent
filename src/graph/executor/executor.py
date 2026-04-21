"""
Unified executor: ``execute_step(step, context) -> StepResult``.

Consumes ``step["instruction"]`` only; enforces non-empty instruction; routes via the
router registry (canonical owner).

Each ``_run_<owner>`` handler adapts ``step`` + ``context`` into the sub-agent's
**Pydantic request schema**, calls the sub-agent's typed ``invoke`` entry point, and
adapts the **Pydantic response schema** back into ``StepResult``. This is the
architectural seam we can split into independent services later with zero business-
logic churn — the sub-agents already speak JSON contracts.
"""
import time
from typing import Any

from src.graph.executor.schema import StepResult, ExecutionContext
from src.graph.executor.router import get_canonical, register, ROUTER, supported_owners


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
    """Single place to build StepResult."""
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
    from src.graph.sql_agent.pipeline import invoke as invoke_sql
    from src.graph.sql_agent.schema import SqlAgentRequest, SqlAgentResponse
    from src.graph.sql_agent.utils.transaction_template import (
        _instruction_looks_like_transaction_retrieval,
        _parse_date_range,
        run_transaction_retrieval_template,
    )
    from src.utils.db import get_engine
    from src.graph.sql_agent.config import get_table_name

    instruction = _instruction_from_step(step)
    user_id = context.get("current_user_id") or ""

    # Fast path: transaction retrieval template bypasses the LLM entirely.
    if user_id and _instruction_looks_like_transaction_retrieval(instruction):
        start_end = _parse_date_range(instruction)
        if start_end:
            start_date, end_date = start_end
            engine = get_engine()
            table_name = get_table_name()
            rows, err, truncated = run_transaction_retrieval_template(
                engine, table_name, user_id, start_date, end_date
            )
            if err:
                resp = SqlAgentResponse(status="error", error=err)
            else:
                summary = f"Retrieved {len(rows or [])} transaction(s)."
                if truncated:
                    summary += " (Capped at 1000 rows.)"
                resp = SqlAgentResponse(
                    status="ok",
                    summary=summary,
                    sql="(transaction retrieval template)",
                    result=rows,
                    row_count=len(rows or []),
                    truncated=truncated,
                )
            return _sql_response_to_step_result(step, resp)

    req = SqlAgentRequest(
        instruction=instruction,
        current_user_id=user_id,
    )
    resp = invoke_sql(req)
    return _sql_response_to_step_result(step, resp)


def _sql_response_to_step_result(step: dict[str, Any], resp: Any) -> StepResult:
    return _build_result(
        step,
        status=resp.status,
        summary=resp.summary,
        artifacts={"sql": resp.sql, "result": resp.result},
        error_message=resp.error or "",
        agent_name="sql_agent",
    )


def _run_rag(step: dict[str, Any], context: ExecutionContext) -> StepResult:
    from src.graph.rag_agent.pipeline import invoke as invoke_rag
    from src.graph.rag_agent.schema import RagAgentRequest

    req = RagAgentRequest(
        instruction=_instruction_from_step(step),
        namespace=context.get("namespace"),
    )
    resp = invoke_rag(req)
    return _build_result(
        step,
        status=resp.status,
        summary=resp.summary,
        artifacts={
            "citations": resp.citations,
            "route_decision": resp.route_decision,
        },
        error_message=resp.error or "",
        agent_name="rag_agent",
    )


def _extract_dep_step_id(dep: Any) -> str:
    if isinstance(dep, str):
        return (dep or "").strip()
    if isinstance(dep, dict):
        return (dep.get("step_id") or dep.get("step") or "").strip()
    return ""


def _pick_upstream_sql_rows(
    step: dict[str, Any],
    prev_results: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Find the most relevant upstream SQL rows for a fraud step.

    Preference order:
      1) explicit ``depends_on`` (whichever completed ok and has ``artifacts.result`` list)
      2) fallback: any prior ok step with an ``artifacts.result`` list
    """
    for dep in step.get("depends_on") or []:
        dep_id = _extract_dep_step_id(dep)
        if not dep_id:
            continue
        sr = prev_results.get(dep_id) or {}
        if sr.get("status") != "ok":
            continue
        artifacts = (sr.get("data") or {}).get("artifacts") or {}
        rows = artifacts.get("result")
        if isinstance(rows, list):
            return rows, ((sr.get("data") or {}).get("summary") or "").strip()

    for _sid, sr in prev_results.items():
        if (sr or {}).get("status") != "ok":
            continue
        artifacts = ((sr or {}).get("data") or {}).get("artifacts") or {}
        rows = artifacts.get("result")
        if isinstance(rows, list):
            return rows, (((sr or {}).get("data") or {}).get("summary") or "").strip()

    return None, None


def _run_fraud(step: dict[str, Any], context: ExecutionContext) -> StepResult:
    import logging

    from src.graph.fraud_agent.pipeline import invoke as invoke_fraud
    from src.graph.fraud_agent.schema import FraudAgentRequest

    logger = logging.getLogger(__name__)

    instruction = _instruction_from_step(step)
    user_id = context.get("current_user_id") or ""
    prev_results = context.get("previous_step_results") or {}

    logger.info(
        "fraud_executor: step_id=%s prev_results_keys=%s depends_on=%s",
        step.get("id"),
        list(prev_results.keys()),
        [_extract_dep_step_id(d) for d in (step.get("depends_on") or [])],
    )

    initial_sql_result, initial_sql_answer = _pick_upstream_sql_rows(step, prev_results)

    logger.info(
        "fraud_executor: step_id=%s initial_sql_result_set=%s initial_len=%s",
        step.get("id"),
        initial_sql_result is not None,
        len(initial_sql_result) if initial_sql_result is not None else 0,
    )

    instruction_for_agent = instruction
    if initial_sql_result is not None:
        instruction_for_agent = (
            f"{instruction}\n\n"
            "(Transaction data from the previous step is already loaded; "
            "call analyze_risk_scores_batch with input 'use last result' to score it.)"
        )

    req = FraudAgentRequest(
        instruction=instruction_for_agent,
        current_user_id=user_id,
        initial_sql_result=initial_sql_result,
        initial_sql_answer=initial_sql_answer,
    )
    resp = invoke_fraud(req)
    return _build_result(
        step,
        status=resp.status,
        summary=resp.summary,
        artifacts={
            "risk_scores": resp.risk_scores,
            "profile": resp.profile,
        },
        error_message=resp.error or "",
        agent_name="fraud_agent",
    )


# Register only canonical owners so trace / aggregation see one format.
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
    """Execute one plan step. Normalizes owner → canonical → dispatches via ROUTER."""
    step_id = step.get("id") or ""
    owner_raw = (step.get("owner") or "").strip()
    owner_canonical = get_canonical(owner_raw)

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
