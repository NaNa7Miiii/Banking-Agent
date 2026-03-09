"""
Init orchestration: build normalized_steps, empty step_results, execution_context, and reset derived sets.
Called after planner; after replan (maybe_replan) re-enters with existing step_results and merged plan.
"""
from typing import Any

from refactored.graph.runtime_state import RuntimeState
from refactored.graph.nodes.select_ready_steps import _recompute_completed_failed


def init_orchestration_node(state: RuntimeState) -> RuntimeState:
    """
    Initialize execution state from plan. Sets normalized_steps (copy of plan.steps with status),
    step_results (empty on first run; preserved on replan re-entry), execution_context, and derived sets.
    On replan re-entry (existing step_results and replan_count > 0): do not clear step_results;
    set each step's status from step_results (done vs todo) and recompute completed/failed.
    """
    plan = state.get("plan")
    if not plan or not plan.get("steps"):
        return {
            "normalized_steps": [],
            "step_results": {},
            "execution_context": {"current_user_id": state.get("customer_id_number") or ""},
            "ready_step_ids": [],
            "completed_step_ids": [],
            "failed_step_ids": [],
            "current_parallel_groups": [],
            "replan_count": 0,
            "max_replan": 2,
        }

    steps = plan.get("steps") or []
    existing_step_results = state.get("step_results") or {}
    replan_count = state.get("replan_count") or 0
    is_replan_reentry = bool(existing_step_results) and replan_count > 0

    normalized_steps: list[dict[str, Any]] = []
    for s in steps:
        step = dict(s)
        if step.get("status") is None:
            if is_replan_reentry and (existing_step_results.get(step.get("id")) or {}).get("status") == "ok":
                step["status"] = "done"
            else:
                step["status"] = "todo"
        normalized_steps.append(step)

    execution_context: dict[str, Any] = state.get("execution_context") or {
        "current_user_id": state.get("customer_id_number") or "",
    }

    if is_replan_reentry:
        completed, failed = _recompute_completed_failed(normalized_steps, existing_step_results)
        return {
            "normalized_steps": normalized_steps,
            "step_results": existing_step_results,
            "execution_context": execution_context,
            "ready_step_ids": [],
            "completed_step_ids": completed,
            "failed_step_ids": failed,
            "current_parallel_groups": [],
            "replan_count": replan_count,
            "max_replan": state.get("max_replan") or 2,
        }

    return {
        "normalized_steps": normalized_steps,
        "step_results": {},
        "execution_context": execution_context,
        "ready_step_ids": [],
        "completed_step_ids": [],
        "failed_step_ids": [],
        "current_parallel_groups": [],
        "replan_count": 0,
        "max_replan": 2,
    }
