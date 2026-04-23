"""
Maybe replan: if should_replan, increment replan_count and (full) call planner with replan context,
merge new remaining plan with completed steps, preserve step_results for completed only; then route to init_orchestration.
P0-3: Step id conflict resolution (rename new steps that clash with completed), DAG/ref validation after merge.
"""
import json
import logging
from typing import Any

from src.graph.runtime_state import RuntimeState
from src.models.llm import get_llm
from src.utils.prompt_loader import load_system_prompt
from src.graph.executor.router import get_canonical, canonical_owners


logger = logging.getLogger(__name__)
PLANNER_MODULE = "planner"


def _parse_plan_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    return json.loads(cleaned)


def _ensure_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _normalize_replan_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize step dicts for replan output (same contract as planner)."""
    out = []
    for step in steps:
        s = dict(step)
        if s.get("depends_on") is None:
            s["depends_on"] = []
        if s.get("status") is None:
            s["status"] = "todo"
        s["inputs_needed"] = _ensure_string_list(s.get("inputs_needed"))
        s["actions"] = _ensure_string_list(s.get("actions"))
        s["expected_outputs"] = _ensure_string_list(s.get("expected_outputs"))
        s["acceptance_criteria"] = _ensure_string_list(s.get("acceptance_criteria"))
        s["fallback"] = _ensure_string_list(s.get("fallback"))
        if not (s.get("instruction") or "").strip():
            s["instruction"] = (s.get("title") or "").strip()
        s["owner"] = get_canonical(s.get("owner") or "")
        out.append(s)
    return out


def _prune_illegal_owner_new_steps(new_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Defense-in-depth mirror of planner._prune_illegal_owner_steps: drop any new
    replan step whose owner isn't a registered sub-agent and scrub dangling
    depends_on references in the kept steps. Dependencies on previously
    completed steps (original plan ids) are untouched.
    """
    legal = canonical_owners()
    kept: list[dict[str, Any]] = []
    dropped_ids: set[str] = set()
    for step in new_steps:
        if step.get("owner") in legal:
            kept.append(step)
        else:
            sid = (step.get("id") or "").strip()
            if sid:
                dropped_ids.add(sid)
            logger.warning(
                "Replan emitted step %s with unsupported owner %r; dropping. Legal owners: %s",
                step.get("id"),
                step.get("owner"),
                sorted(legal),
            )
    if not dropped_ids:
        return kept
    for step in kept:
        step["depends_on"] = [
            d for d in (step.get("depends_on") or [])
            if _extract_dep_step_id(d) not in dropped_ids
        ]
    return kept


def _call_replan_llm(user_message: str) -> dict[str, Any]:
    """Load replan system prompt, call LLM, parse JSON plan (goal + steps)."""
    system_prompt = load_system_prompt(PLANNER_MODULE, "replan_system.md")
    llm = get_llm(role="planner")
    raw = llm.chat(system_prompt=system_prompt, user_prompt=user_message)
    return _parse_plan_json(raw)


def _extract_dep_step_id(dep: Any) -> str:
    if isinstance(dep, str):
        return (dep or "").strip()
    if isinstance(dep, dict):
        return (dep.get("step_id") or dep.get("step") or "").strip()
    return ""


def _resolve_replan_step_id_conflicts(
    new_steps: list[dict[str, Any]],
    completed_step_ids: set[str],
    replan_count: int,
) -> list[dict[str, Any]]:
    """
    Hard rule: completed steps cannot be overwritten. Rename any new step whose id
    is in completed_step_ids to replan_{replan_count}_step_{i+1}; update depends_on in new_steps to use new ids.
    """
    out: list[dict[str, Any]] = []
    id_rewrite: dict[str, str] = {}
    for i, step in enumerate(new_steps):
        s = dict(step)
        step_id = (s.get("id") or "").strip()
        new_id = step_id
        if step_id and step_id in completed_step_ids:
            new_id = f"replan_{replan_count}_step_{i + 1}"
            id_rewrite[step_id] = new_id
        s["id"] = new_id
        out.append(s)
    if not id_rewrite:
        return out
    for s in out:
        deps = s.get("depends_on") or []
        new_deps = []
        for d in deps:
            dep_id = _extract_dep_step_id(d)
            new_id = id_rewrite.get(dep_id, dep_id)
            if isinstance(d, dict):
                new_deps.append({**d, "step_id": new_id} if "step_id" in d else {"step_id": new_id})
            else:
                new_deps.append(new_id)
        s["depends_on"] = new_deps
    return out


def _validate_merged_plan(merged_steps: list[dict[str, Any]], plan: dict[str, Any]) -> tuple[bool, str]:
    """
    DAG and reference integrity: all depends_on refer to existing step ids; join_points refer to existing groups/steps; no cycle.
    Returns (ok, error_message).
    """
    step_ids = {(s.get("id") or "").strip() for s in merged_steps if (s.get("id") or "").strip()}
    if len(step_ids) != sum(1 for s in merged_steps if (s.get("id") or "").strip()):
        return False, "Duplicate step ids in merged plan"

    for step in merged_steps:
        step_id = (step.get("id") or "").strip()
        if not step_id:
            continue
        for dep in step.get("depends_on") or []:
            dep_id = _extract_dep_step_id(dep)
            if dep_id and dep_id not in step_ids:
                return False, f"Step {step_id} depends_on missing step_id: {dep_id}"

    join_points = plan.get("join_points") or []
    group_ids = set()
    for s in merged_steps:
        pg = s.get("parallel_group")
        if isinstance(pg, str) and pg.strip():
            group_ids.add(pg.strip())
    for jp in join_points:
        apg = (jp.get("after_parallel_group") or "").strip()
        if apg and apg not in group_ids:
            return False, f"join_point after_parallel_group not found: {apg}"
        merge_ids = jp.get("merge_artifacts_from_steps") or []
        for mid in merge_ids:
            mid = (mid if isinstance(mid, str) else str(mid)).strip()
            if mid and mid not in step_ids:
                return False, f"join_point merge_artifacts_from_steps references missing step: {mid}"

    # DAG: no cycle (toposort). in_degree[x] = number of steps that have x in depends_on (edges into x)
    from collections import deque
    in_degree: dict[str, int] = {sid: 0 for sid in step_ids}
    for step in merged_steps:
        step_id = (step.get("id") or "").strip()
        for dep in step.get("depends_on") or []:
            dep_id = _extract_dep_step_id(dep)
            if dep_id in step_ids:
                in_degree[dep_id] = in_degree.get(dep_id, 0) + 1
    q: deque[str] = deque(sid for sid in step_ids if in_degree[sid] == 0)
    seen = 0
    while q:
        n = q.popleft()
        seen += 1
        for step in merged_steps:
            if (step.get("id") or "").strip() != n:
                continue
            for dep in step.get("depends_on") or []:
                dep_id = _extract_dep_step_id(dep)
                if dep_id in step_ids:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        q.append(dep_id)
            break
    if seen != len(step_ids):
        return False, "Cycle or invalid dependency in merged plan steps"

    return True, ""


def maybe_replan_node(state: RuntimeState) -> RuntimeState:
    """
    If not should_replan: no-op (return {}).
    Else: increment replan_count; (full) call planner with replan context, merge new remaining steps
    with completed steps, keep step_results only for completed; return updated plan, step_results, replan_count.
    Always routes to init_orchestration (handled by graph edge).
    """
    if not state.get("should_replan"):
        return {}

    # Only increment replan_count when we successfully apply a merged plan (not on LLM or validation failure)
    current_replan_count = state.get("replan_count") or 0
    plan = state.get("plan") or {}
    normalized_steps = state.get("normalized_steps") or []
    step_results = state.get("step_results") or {}
    completed_step_ids = set(state.get("completed_step_ids") or [])
    failed_step_ids = state.get("failed_step_ids") or []
    replan_reason = state.get("replan_reason") or "step failed"
    user_input = state.get("user_input") or (plan.get("goal") or "")

    use_full_replan = True
    if not use_full_replan:
        return {
            "replan_count": current_replan_count,
        }

    # Full replan: build context and call replan LLM (StepResult has data.summary, data.artifacts)
    completed_summary = []
    for sid in (state.get("completed_step_ids") or []):
        res = step_results.get(sid) or {}
        data = res.get("data") or {}
        art = data.get("artifacts")
        summ = (data.get("summary") or "").strip()
        summary = f"- {sid}: " + (summ[:200] if summ else (str(art)[:200] if art else "ok"))
        completed_summary.append(summary)
    user_message = (
        f"Original user goal: {user_input}\n\n"
        f"Completed steps and their results:\n" + "\n".join(completed_summary) + "\n\n"
        f"Failed step(s): {failed_step_ids}\n"
        f"Reason: {replan_reason}\n\n"
        "Output a JSON object with keys: goal, steps. Steps must be only the NEW steps for remaining work, with ids like replan_1_step_1, replan_1_step_2."
    )
    try:
        new_plan = _call_replan_llm(user_message)
    except Exception:
        # On LLM/parse failure, re-enter init with same plan without consuming a replan attempt
        return {"replan_count": current_replan_count}

    new_steps = new_plan.get("steps") or []
    new_steps = _normalize_replan_steps(new_steps)
    # Defense-in-depth: the replan LLM sometimes emits owners like
    # `banking_assistant` or `main` for summarization; the executor rejects
    # them. Drop these here, scrub dangling depends_on in the survivors, and
    # bail gracefully if nothing runnable remains.
    new_steps = _prune_illegal_owner_new_steps(new_steps)
    if not new_steps:
        logger.warning(
            "Replan produced no steps with legal owners; skipping this replan attempt."
        )
        return {"replan_count": current_replan_count}
    # P0-3: completed steps cannot be overwritten; rename new steps that conflict with completed ids
    new_steps = _resolve_replan_step_id_conflicts(new_steps, completed_step_ids, current_replan_count + 1)

    completed_step_dicts = [dict(s) for s in normalized_steps if (s.get("id") or "").strip() in completed_step_ids]
    merged_steps = completed_step_dicts + new_steps
    merged_plan = {
        **plan,
        "goal": new_plan.get("goal") or plan.get("goal"),
        "steps": merged_steps,
    }

    # P0-3: DAG and reference integrity validation
    ok, err = _validate_merged_plan(merged_steps, merged_plan)
    if not ok:
        logger.warning("Replan validation failed: %s. Re-entering init with same plan.", err)
        return {"replan_count": current_replan_count}

    step_results_kept = {k: v for k, v in step_results.items() if k in completed_step_ids}

    return {
        "plan": merged_plan,
        "step_results": step_results_kept,
        "replan_count": current_replan_count + 1,
    }
