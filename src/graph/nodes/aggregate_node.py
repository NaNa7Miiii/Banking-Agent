"""
Aggregate: call aggregate_results(user_goal, step_results, plan) and set final_answer.
Tolerates partial execution (failed or missing steps).
"""
from src.graph.orchestrator.aggregation import aggregate_results
from src.graph.runtime_state import RuntimeState


def aggregate_node(state: RuntimeState) -> RuntimeState:
    """
    Produce final_answer from successful step results. Uses existing aggregate_results
    which already aggregates only status == "ok" and does not crash on missing/failed steps.
    """
    user_goal = state.get("user_input") or ""
    step_results = state.get("step_results") or {}
    plan = state.get("plan") or {}

    final_answer = aggregate_results(user_goal, step_results, plan)
    return {
        "final_answer": final_answer,
    }
