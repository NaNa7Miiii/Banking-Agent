"""
Orchestrator loop: pick next step -> execute -> update state -> continue / finalize.
Replan supported with replan_count cap.
"""
from typing import Any

from refactored.graph.executor import execute_step, StepResult, ExecutionContext
from refactored.graph.orchestrator.aggregation import aggregate_results


def _steps_with_status(plan: list[dict]) -> list[dict]:
    """Return a mutable copy of plan steps, ensuring each has status."""
    out = []
    for s in plan:
        step = dict(s)
        if step.get("status") is None:
            step["status"] = "todo"
        out.append(step)
    return out


def _pick_next_step(steps: list[dict], step_results: dict[str, StepResult]) -> dict | None:
    """
    Return the next step that is todo and whose depends_on are all satisfied (present in step_results with status ok).
    """
    done_ids = {sid for sid, sr in step_results.items() if (sr or {}).get("status") == "ok"}
    for step in steps:
        if (step.get("status") or "") != "todo":
            continue
        step_id = step.get("id") or ""
        deps = step.get("depends_on") or []
        if all((d.get("step_id") or "") in done_ids for d in deps):
            return step
    return None


def run_orchestrator_loop(
    plan: dict[str, Any],
    user_goal: str,
    context: ExecutionContext,
    max_replan: int = 2,
) -> tuple[str, dict[str, Any]]:
    """
    Execute the plan step by step; aggregate and return (final_answer, execution_state).
    On step error we continue (mark failed); when no next step we aggregate and finalize.
    Replan: if a step fails and replan_count < max_replan, caller can call planner again and re-invoke (not done inside here for simplicity).
    """
    steps = _steps_with_status(plan.get("steps") or [])
    step_results: dict[str, StepResult] = {}
    replan_count = 0

    while True:
        next_step = _pick_next_step(steps, step_results)
        if next_step is None:
            break
        step_id = next_step.get("id") or ""
        result = execute_step(next_step, context)
        step_results[step_id] = result
        next_step["status"] = "done" if (result.get("status") == "ok") else "failed"
        # Optional: on critical failure trigger replan by returning early with replan signal (caller handles)
        # Here we only continue until no more runnable steps.

    final_answer = aggregate_results(user_goal, step_results, plan)
    state: dict[str, Any] = {
        "plan": plan,
        "step_results": step_results,
        "replan_count": replan_count,
        "final_answer": final_answer,
    }
    return final_answer, state
