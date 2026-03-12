"""
Evaluate progress: set should_aggregate, should_replan, replan_reason.
If any step failed and replan_count < max_replan → should_replan; else → should_aggregate (incl. partial).
"""
from src.graph.runtime_state import RuntimeState
from src.graph.nodes.select_ready_steps import _recompute_completed_failed


def evaluate_progress_node(state: RuntimeState) -> RuntimeState:
    """
    We only enter this node when select_ready_steps returned 0 ready steps.
    Recompute completed/failed from step_results and normalized_steps; then:
    - If all steps done (no todo left) → should_aggregate = True.
    - If any failed and replan_count < max_replan → should_replan = True, set replan_reason.
    - Else → should_aggregate = True (partial aggregate when replan cap reached or no failure).
    """
    normalized_steps = state.get("normalized_steps") or []
    step_results = state.get("step_results") or {}
    replan_count = state.get("replan_count") or 0
    max_replan = state.get("max_replan") or 2

    completed, failed = _recompute_completed_failed(normalized_steps, step_results)
    failed_set = set(failed)
    step_ids = {(s.get("id") or "").strip() for s in normalized_steps if (s.get("id") or "").strip()}
    all_done = step_ids <= (set(completed) | set(failed)) if step_ids else True
    if all_done:
        return {
            "completed_step_ids": completed,
            "failed_step_ids": failed,
            "should_aggregate": True,
            "should_replan": False,
            "replan_reason": "",
        }

    has_failed = len(failed_set) > 0
    can_replan = replan_count < max_replan
    if has_failed and can_replan:
        first_failed = next(iter(failed_set), "")
        return {
            "completed_step_ids": completed,
            "failed_step_ids": failed,
            "should_aggregate": False,
            "should_replan": True,
            "replan_reason": first_failed or "step failed",
        }

    return {
        "completed_step_ids": completed,
        "failed_step_ids": failed,
        "should_aggregate": True,
        "should_replan": False,
        "replan_reason": "",
    }
