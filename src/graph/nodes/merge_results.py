"""
Merge step results: after a parallel group wave, write a synthetic step result into step_results
and add a synthetic step to normalized_steps so downstream deps (depends_on synthetic_id) resolve.
Deterministic merge only: list concat for artifacts, string concat for summary. No semantic synthesis.
"""
import time
from typing import Any

from src.graph.executor.schema import StepResult
from src.graph.runtime_state import RuntimeState


def _merge_artifacts_and_summary(
    step_results: dict[str, StepResult],
    step_ids: list[str],
) -> tuple[dict[str, Any], str]:
    """Deterministic merge: concat lists for artifacts, concat summaries."""
    summaries: list[str] = []
    artifact_lists: list[Any] = []
    artifact_dicts: list[dict[str, Any]] = []

    for step_id in step_ids:
        sr = step_results.get(step_id) or {}
        data = sr.get("data") or {}
        summary = (data.get("summary") or "").strip()
        if summary:
            summaries.append(summary)
        artifacts = data.get("artifacts")
        if isinstance(artifacts, list):
            artifact_lists.append(artifacts)
        elif isinstance(artifacts, dict):
            artifact_dicts.append(artifacts)

    merged_summary = "\n\n".join(summaries) if summaries else ""
    merged_artifacts: dict[str, Any] = {}
    if artifact_lists:
        merged_artifacts["items"] = [x for sub in artifact_lists for x in sub]
    for d in artifact_dicts:
        for k, v in d.items():
            if k not in merged_artifacts:
                merged_artifacts[k] = v
            elif isinstance(merged_artifacts[k], list) and isinstance(v, list):
                merged_artifacts[k] = merged_artifacts[k] + v
            else:
                merged_artifacts[k] = v

    return merged_artifacts, merged_summary


def merge_step_results_node(state: RuntimeState) -> RuntimeState:
    """
    If current_parallel_groups is set and the wave (ready_step_ids) all succeeded,
    find the join_point, merge artifacts/summary, write synthetic step result and synthetic step.
    Called only when the previous execute wave was a full parallel group and all steps are ok.
    """
    current_parallel_groups = state.get("current_parallel_groups") or []
    step_results = dict(state.get("step_results") or {})
    normalized_steps = list(state.get("normalized_steps") or [])
    plan = state.get("plan") or {}
    join_points = plan.get("join_points") or []
    ready_step_ids = state.get("ready_step_ids") or []

    if not current_parallel_groups or not ready_step_ids:
        return {}

    group_id = current_parallel_groups[0]
    join_point = None
    for jp in join_points:
        if (jp.get("after_parallel_group") or "") == group_id:
            join_point = jp
            break

    step_ids_to_merge = (join_point.get("merge_artifacts_from_steps") or []) if join_point else ready_step_ids
    if not step_ids_to_merge:
        step_ids_to_merge = ready_step_ids

    if any((step_results.get(sid) or {}).get("status") != "ok" for sid in step_ids_to_merge):
        return {}

    merged_artifacts, merged_summary = _merge_artifacts_and_summary(step_results, step_ids_to_merge)
    synthetic_id = f"join_{group_id}" if group_id else "join_1"

    synthetic_result: StepResult = {
        "step_id": synthetic_id,
        "owner": "join",
        "status": "ok",
        "data": {"summary": merged_summary, "artifacts": merged_artifacts},
        "error_message": "",
        "metadata": {"agent": "join", "owner": "join", "timestamp": time.time()},
    }
    step_results[synthetic_id] = synthetic_result
    normalized_steps.append({"id": synthetic_id, "status": "done"})

    return {
        "step_results": step_results,
        "normalized_steps": normalized_steps,
    }
