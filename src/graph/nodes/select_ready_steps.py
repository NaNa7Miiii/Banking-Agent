"""
Select ready steps: recompute completed/failed from step_results (single source of truth);
then compute ready_step_ids (todo steps whose depends_on are all in completed_step_ids).
normalized_steps.status is cache/display only; use reconcile_step_status() as the single place to write it.
"""
from typing import Any

from src.graph.executor.schema import StepResult
from src.graph.runtime_state import RuntimeState


def _dep_step_id(dep: Any) -> str:
    """Extract step_id from depends_on item (dict with step_id or plain string)."""
    if isinstance(dep, dict):
        return (dep.get("step_id") or dep.get("step") or "").strip()
    if isinstance(dep, str):
        return (dep or "").strip()
    return ""


def reconcile_step_status(
    normalized_steps: list[dict[str, Any]],
    step_results: dict[str, StepResult],
) -> list[dict[str, Any]]:
    """
    Single point to write normalized_steps.status from step_results (source of truth).
    ok -> done, error -> failed, no result -> todo. Returns new list; does not mutate input.
    """
    out: list[dict[str, Any]] = []
    for step in normalized_steps:
        s = dict(step)
        step_id = (s.get("id") or "").strip()
        if not step_id:
            out.append(s)
            continue
        sr = step_results.get(step_id) or {}
        st = (sr.get("status") or "").strip().lower()
        if st == "ok":
            s["status"] = "done"
        elif st == "error":
            s["status"] = "failed"
        else:
            s["status"] = "todo"
        out.append(s)
    return out


def _recompute_completed_failed(
    normalized_steps: list[dict[str, Any]],
    step_results: dict[str, StepResult],
) -> tuple[list[str], list[str]]:
    """Derive completed_step_ids and failed_step_ids from step_results only (source of truth)."""
    completed: list[str] = []
    failed: list[str] = []
    for step in normalized_steps:
        step_id = (step.get("id") or "").strip()
        if not step_id:
            continue
        sr = step_results.get(step_id) or {}
        st = (sr.get("status") or "").strip().lower()
        if st == "ok":
            completed.append(step_id)
        elif st == "error":
            failed.append(step_id)
    return completed, failed


def select_ready_steps_node(state: RuntimeState) -> RuntimeState:
    """
    Recompute completed_step_ids, failed_step_ids; then compute ready_step_ids.
    Steps with same non-null parallel_group run together only when the whole group is ready.
    If a full group is ready, wave = that group; else wave = one ready step without a group (or first ready).
    """
    normalized_steps = state.get("normalized_steps") or []
    step_results = state.get("step_results") or {}

    completed, failed = _recompute_completed_failed(normalized_steps, step_results)
    completed_set = set(completed)
    failed_set = set(failed)

    # All step_ids that are todo (not in completed/failed per step_results) and deps satisfied
    ready_set: set[str] = set()
    ready_candidates: list[tuple[str, str | None]] = []  # (step_id, parallel_group or None)
    for step in normalized_steps:
        step_id = (step.get("id") or "").strip()
        if not step_id or step_id in completed_set or step_id in failed_set:
            continue
        deps = step.get("depends_on") or []
        if all(_dep_step_id(d) in completed_set for d in deps):
            pg = step.get("parallel_group")
            pg_val = pg.strip() if isinstance(pg, str) and pg.strip() else None
            ready_candidates.append((step_id, pg_val))
            ready_set.add(step_id)

    # Full groups from normalized_steps: group_id -> all step ids with that parallel_group
    from collections import defaultdict
    group_to_all_ids: dict[str, list[str]] = defaultdict(list)
    for step in normalized_steps:
        step_id = (step.get("id") or "").strip()
        pg = step.get("parallel_group")
        if isinstance(pg, str) and pg.strip():
            group_to_all_ids[pg.strip()].append(step_id)

    ready_step_ids: list[str] = []
    current_parallel_groups: list[str] = []

    # Prefer one full parallel group: group is ready only when every step in that group is in ready_set
    for group_id in sorted(group_to_all_ids.keys()):
        ids = group_to_all_ids[group_id]
        if not ids:
            continue
        if all(sid in ready_set for sid in ids):
            ready_step_ids = ids
            current_parallel_groups = [group_id]
            break
    else:
        # No full group ready; steps in an incomplete group cannot run alone
        incomplete = set()
        for group_id, ids in group_to_all_ids.items():
            if any(sid in ready_set for sid in ids) and not all(sid in ready_set for sid in ids):
                incomplete.update(ids)
        ungrouped = [sid for sid, pg in ready_candidates if not pg and sid not in incomplete]
        if ungrouped:
            ready_step_ids = [ungrouped[0]]

    return {
        "completed_step_ids": completed,
        "failed_step_ids": failed,
        "ready_step_ids": ready_step_ids,
        "current_parallel_groups": current_parallel_groups,
    }
