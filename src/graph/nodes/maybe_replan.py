"""
Maybe replan: if should_replan, increment replan_count and (full) call planner with replan context,
merge new remaining plan with completed steps, preserve step_results for completed only; then route to init_orchestration.
Phase 3: replace-remaining only; always routes to init_orchestration.
"""
import json
from typing import Any

from src.graph.runtime_state import RuntimeState
from src.models.llm import get_llm
from src.utils.prompt_loader import load_system_prompt
from src.graph.executor.router import get_canonical


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


def _call_replan_llm(user_message: str) -> dict[str, Any]:
    """Load replan system prompt, call LLM, parse JSON plan (goal + steps)."""
    system_prompt = load_system_prompt(PLANNER_MODULE, "replan_system.md")
    llm = get_llm(role="planner")
    raw = llm.chat(system_prompt=system_prompt, user_prompt=user_message)
    return _parse_plan_json(raw)


def maybe_replan_node(state: RuntimeState) -> RuntimeState:
    """
    If not should_replan: no-op (return {}).
    Else: increment replan_count; (full) call planner with replan context, merge new remaining steps
    with completed steps, keep step_results only for completed; return updated plan, step_results, replan_count.
    Always routes to init_orchestration (handled by graph edge).
    """
    if not state.get("should_replan"):
        return {}

    replan_count = (state.get("replan_count") or 0) + 1
    plan = state.get("plan") or {}
    normalized_steps = state.get("normalized_steps") or []
    step_results = state.get("step_results") or {}
    completed_step_ids = set(state.get("completed_step_ids") or [])
    failed_step_ids = state.get("failed_step_ids") or []
    replan_reason = state.get("replan_reason") or "step failed"
    user_input = state.get("user_input") or (plan.get("goal") or "")

    # Placeholder: no planner call; just increment replan_count and pass through (init will preserve step_results).
    use_full_replan = True  # Set to False for placeholder-only behavior
    if not use_full_replan:
        return {
            "replan_count": replan_count,
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
        # On LLM/parse failure, behave like placeholder: only increment and re-enter init with same plan
        return {"replan_count": replan_count}

    new_steps = new_plan.get("steps") or []
    new_steps = _normalize_replan_steps(new_steps)
    completed_step_dicts = [dict(s) for s in normalized_steps if (s.get("id") or "") in completed_step_ids]
    for d in completed_step_dicts:
        d["status"] = "done"
    merged_steps = completed_step_dicts + new_steps
    merged_plan = {
        **plan,
        "goal": new_plan.get("goal") or plan.get("goal"),
        "steps": merged_steps,
    }
    step_results_kept = {k: v for k, v in step_results.items() if k in completed_step_ids}

    return {
        "plan": merged_plan,
        "step_results": step_results_kept,
        "replan_count": replan_count,
    }
