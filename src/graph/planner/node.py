"""
Planner node: load prompt, call LLM, parse and validate JSON plan. No execution; loose coupling.
"""
import json
import logging
from typing import Any

from src.graph.planner.state import PlannerState, Plan
from src.graph.executor.router import get_canonical, canonical_owners
from src.models.llm import get_llm
from src.utils.prompt_loader import load_system_prompt
from src.graph.planner.utils.schema_validator import load_schema, validate_plan

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
    """Coerce to list of strings. LLM sometimes returns a single string for array fields."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _normalize_join_points(join_points: list[dict[str, Any]]) -> None:
    """
    Coerce join_points to match schema. LLM sometimes returns after_parallel_group
    as an array of step ids; schema expects string. If so, use that list for
    merge_artifacts_from_steps and set after_parallel_group to a string.
    """
    for i, jp in enumerate(join_points):
        apg = jp.get("after_parallel_group")
        if isinstance(apg, list):
            step_ids = [str(x) for x in apg]
            jp["merge_artifacts_from_steps"] = jp.get("merge_artifacts_from_steps") or step_ids
            jp["after_parallel_group"] = "group_" + str(i) if step_ids else ""


def _prune_illegal_owner_steps(plan: dict[str, Any]) -> None:
    """
    Drop steps whose (canonicalized) owner is not supported by the executor.
    Also scrub dangling references so remaining steps stay runnable:
      - `depends_on` entries pointing at dropped steps are removed
      - `next_step_id` pointing at a dropped step falls back to the first kept step
      - `join_points.merge_artifacts_from_steps` drops dropped ids

    The planner occasionally invents owners like `main`, `banking_assistant`, or
    `tool:<x>` for summarization/aggregation steps. Aggregation is the
    aggregator node's job, not a plan step, so those entries are safely pruned.
    """
    legal = canonical_owners()
    steps = plan.get("steps") or []
    kept: list[dict[str, Any]] = []
    dropped_ids: set[str] = set()
    for step in steps:
        if step.get("owner") in legal:
            kept.append(step)
        else:
            sid = step.get("id") or ""
            if sid:
                dropped_ids.add(sid)
            logger.warning(
                "Planner emitted step %s with unsupported owner %r; dropping. Legal owners: %s",
                step.get("id"),
                step.get("owner"),
                sorted(legal),
            )
    if not dropped_ids:
        return
    for step in kept:
        step["depends_on"] = [
            d for d in (step.get("depends_on") or [])
            if (d.get("step_id") or "") not in dropped_ids
        ]
    if (plan.get("next_step_id") or "") in dropped_ids:
        plan["next_step_id"] = kept[0]["id"] if kept else None
    for jp in plan.get("join_points") or []:
        jp["merge_artifacts_from_steps"] = [
            sid for sid in (jp.get("merge_artifacts_from_steps") or [])
            if sid not in dropped_ids
        ]
    plan["steps"] = kept


def _normalize_plan(plan: dict[str, Any]) -> Plan:
    """Ensure required/default fields for steps and join_points; keep schema-compliant."""
    steps = plan.get("steps") or []
    for step in steps:
        if step.get("depends_on") is None:
            step["depends_on"] = []
        if step.get("status") is None:
            step["status"] = "todo"
        step["inputs_needed"] = _ensure_string_list(step.get("inputs_needed"))
        step["actions"] = _ensure_string_list(step.get("actions"))
        step["expected_outputs"] = _ensure_string_list(step.get("expected_outputs"))
        step["acceptance_criteria"] = _ensure_string_list(step.get("acceptance_criteria"))
        step["fallback"] = _ensure_string_list(step.get("fallback"))
        # Executor contract: prefer explicit instruction; fallback to title for backward compatibility
        if not (step.get("instruction") or "").strip():
            step["instruction"] = (step.get("title") or "").strip()
        # Canonical owner so executor and trace use one format (subagent:sql, subagent:rag, subagent:fraud)
        step["owner"] = get_canonical(step.get("owner") or "")
    plan["steps"] = steps
    # Defense-in-depth: even if the prompt or schema is misaligned, never let an
    # unsupported owner reach the executor.
    _prune_illegal_owner_steps(plan)
    join_points = plan.get("join_points") or []
    _normalize_join_points(join_points)
    plan["join_points"] = join_points
    return plan


def create_planner_node(*, validate: bool = True):
    """
    Returns a node function (state) -> state that:
    - Loads system prompt from prompts/planner/system.md
    - Calls LLM with user_input as user message
    - Parses JSON, optionally validates against output_schema.json, writes to state["plan"]
    """
    system_prompt = load_system_prompt(PLANNER_MODULE)
    schema = load_schema(PLANNER_MODULE) if validate else None

    def planner_node(state: PlannerState) -> PlannerState:
        user_input = state.get("user_input", "")
        if not user_input:
            return {**state, "plan": None}

        llm = get_llm(role="planner")
        raw = llm.chat(system_prompt=system_prompt, user_prompt=user_input)
        try:
            plan = _parse_plan_json(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Planner LLM output was not valid JSON: %s. Raw (truncated): %s", e, (raw or "")[:500])
            return {**state, "plan": None, "plan_error": "Plan parsing failed."}

        plan = _normalize_plan(plan)

        if validate:
            try:
                validate_plan(plan, schema=schema)
            except Exception as e:
                logger.warning("Planner output failed schema validation: %s", e)
                return {**state, "plan": None, "plan_error": "Plan validation failed."}

        return {**state, "plan": plan}

    return planner_node
