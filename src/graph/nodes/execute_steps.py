"""
Execute ready steps: for each step_id in ready_step_ids, call execute_step(step, context).
Uses ThreadPoolExecutor when the wave has multiple steps (e.g. parallel_group); single step runs inline.
Writes only step_results and step status in normalized_steps; does not write derived sets.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.graph.executor import execute_step, ExecutionContext
from src.graph.runtime_state import RuntimeState
from src.graph.nodes.select_ready_steps import reconcile_step_status
from src.utils.env import get_env

# Max concurrent steps per wave (parallel group or multi-step wave). Override with env MAX_CONCURRENT_STEPS.
def _max_concurrent_steps() -> int:
    try:
        return max(1, min(32, int(get_env("MAX_CONCURRENT_STEPS") or "8")))
    except (TypeError, ValueError):
        return 8


def _find_step_by_id(normalized_steps: list[dict[str, Any]], step_id: str) -> dict[str, Any] | None:
    for s in normalized_steps:
        if (s.get("id") or "") == step_id:
            return s
    return None


def _run_one_step(
    step_id: str,
    step: dict[str, Any],
    execution_context: ExecutionContext,
) -> tuple[str, dict[str, Any]]:
    """Run a single step; used by ThreadPoolExecutor. Returns (step_id, result)."""
    result = execute_step(step, execution_context)
    return step_id, result


def execute_ready_steps_node(state: RuntimeState) -> RuntimeState:
    """
    Run execute_step for each step in ready_step_ids. When multiple steps form a wave
    (e.g. parallel_group), run them concurrently via ThreadPoolExecutor; results are
    collected in the main thread and written to step_results / normalized_steps.
    Derived sets are recomputed by select_ready_steps / evaluate_progress.
    """
    import logging
    logger = logging.getLogger(__name__)
    ready_step_ids = state.get("ready_step_ids") or []
    normalized_steps = list(state.get("normalized_steps") or [])
    base_ctx = state.get("execution_context") or {}
    execution_context: ExecutionContext = dict(base_ctx)
    prev = state.get("step_results") or {}
    execution_context["previous_step_results"] = prev
    logger.info(
        "execute_ready_steps: ready_step_ids=%s previous_step_results_keys=%s",
        ready_step_ids,
        list(prev.keys()),
    )
    step_results = dict(prev)

    if not ready_step_ids:
        return {"step_results": step_results, "normalized_steps": normalized_steps}

    # Build (step_id, step) for each ready step; skip missing steps
    tasks: list[tuple[str, dict[str, Any]]] = []
    for step_id in ready_step_ids:
        step = _find_step_by_id(normalized_steps, step_id)
        if step is not None:
            tasks.append((step_id, step))

    if not tasks:
        return {"step_results": step_results, "normalized_steps": normalized_steps}

    if len(tasks) == 1:
        step_id, step = tasks[0]
        _, result = _run_one_step(step_id, step, execution_context)
        results_by_id = {step_id: result}
    else:
        max_workers = min(len(tasks), _max_concurrent_steps())
        step_by_id = {step_id: step for step_id, step in tasks}
        results_by_id: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_one_step, step_id, step, execution_context): step_id
                for step_id, step in tasks
            }
            for fut in as_completed(futures):
                try:
                    step_id, result = fut.result()
                    results_by_id[step_id] = result
                except Exception:
                    step_id = futures[fut]
                    step = step_by_id.get(step_id) or {}
                    results_by_id[step_id] = {
                        "step_id": step_id,
                        "owner": step.get("owner", ""),
                        "status": "error",
                        "data": {"summary": "", "artifacts": {}},
                        "error_message": "Step execution raised an exception",
                        "metadata": {},
                    }

    for step_id, result in results_by_id.items():
        step_results[step_id] = result

    # Single write-back of status: step_results is source of truth; reconcile for display/cache
    normalized_steps = reconcile_step_status(normalized_steps, step_results)

    return {
        "step_results": step_results,
        "normalized_steps": normalized_steps,
    }
