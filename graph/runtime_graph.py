"""
Runtime graph: planner -> init -> select -> execute -> [merge] -> evaluate -> aggregate -> END.
Execute runs each wave (single step or parallel_group) via ThreadPoolExecutor when wave size > 1;
merge_step_results after a full parallel group when all steps ok.
"""
from langgraph.graph import StateGraph, END

from refactored.graph.runtime_state import RuntimeState
from refactored.graph.planner.node import create_planner_node
from refactored.graph.nodes import (
    init_orchestration_node,
    select_ready_steps_node,
    execute_ready_steps_node,
    merge_step_results_node,
    evaluate_progress_node,
    maybe_replan_node,
    aggregate_node,
)


def _after_planner(state: RuntimeState) -> str:
    """Route: if plan has steps -> init_orchestration, else END."""
    plan = state.get("plan")
    if plan and (plan.get("steps") or []):
        return "init_orchestration"
    return "__end__"


def _after_select(state: RuntimeState) -> str:
    """Route: if any ready steps -> execute_ready_steps, else evaluate_progress."""
    ready = state.get("ready_step_ids") or []
    if len(ready) > 0:
        return "execute_ready_steps"
    return "evaluate_progress"


def _after_execute(state: RuntimeState) -> str:
    """Route: if wave was a parallel group and all steps ok -> merge_step_results, else select_ready_steps."""
    current_parallel_groups = state.get("current_parallel_groups") or []
    ready_step_ids = state.get("ready_step_ids") or []
    step_results = state.get("step_results") or {}
    if not current_parallel_groups or not ready_step_ids:
        return "select_ready_steps"
    if all((step_results.get(sid) or {}).get("status") == "ok" for sid in ready_step_ids):
        return "merge_step_results"
    return "select_ready_steps"


def _after_evaluate(state: RuntimeState) -> str:
    """Route: should_aggregate -> aggregate; should_replan -> maybe_replan (Phase 3)."""
    if state.get("should_replan"):
        return "maybe_replan"
    return "aggregate"


def create_runtime_graph():
    """
    Build and compile the graph-native orchestration runtime.
    Execute node runs steps in a wave concurrently (ThreadPoolExecutor); merge after parallel group when all ok.
    """
    builder = StateGraph(RuntimeState)

    builder.add_node("planner", create_planner_node())
    builder.add_node("init_orchestration", init_orchestration_node)
    builder.add_node("select_ready_steps", select_ready_steps_node)
    builder.add_node("execute_ready_steps", execute_ready_steps_node)
    builder.add_node("merge_step_results", merge_step_results_node)
    builder.add_node("evaluate_progress", evaluate_progress_node)
    builder.add_node("maybe_replan", maybe_replan_node)
    builder.add_node("aggregate", aggregate_node)

    builder.set_entry_point("planner")
    builder.add_conditional_edges(
        "planner",
        _after_planner,
        {"init_orchestration": "init_orchestration", "__end__": END},
    )
    builder.add_edge("init_orchestration", "select_ready_steps")
    builder.add_conditional_edges(
        "select_ready_steps",
        _after_select,
        {"execute_ready_steps": "execute_ready_steps", "evaluate_progress": "evaluate_progress"},
    )
    builder.add_conditional_edges(
        "execute_ready_steps",
        _after_execute,
        {"merge_step_results": "merge_step_results", "select_ready_steps": "select_ready_steps"},
    )
    builder.add_edge("merge_step_results", "select_ready_steps")
    builder.add_conditional_edges(
        "evaluate_progress",
        _after_evaluate,
        {"maybe_replan": "maybe_replan", "aggregate": "aggregate"},
    )
    builder.add_edge("maybe_replan", "init_orchestration")
    builder.add_edge("aggregate", END)

    return builder.compile()
