"""
Planner node: load prompt, call LLM, parse and validate JSON plan. No execution; loose coupling.
"""
import json
from typing import Any

from src.graph.planner.state import PlannerState, Plan
from src.graph.executor.router import get_canonical
from src.models.llm import get_llm
from src.utils.prompt_loader import load_system_prompt
from src.graph.planner.utils.schema_validator import load_schema, validate_plan


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
        plan = _parse_plan_json(raw)
        plan = _normalize_plan(plan)

        if validate:
            validate_plan(plan, schema=schema)

        return {**state, "plan": plan}

    return planner_node
