"""
Graph: entry and orchestration. Entry -> planner -> END (orchestrator runs executor separately).
"""
from langgraph.graph import StateGraph, END

from src.graph.planner.state import PlannerState
from src.graph.planner.node import create_planner_node


def create_plan_only_graph():
    """
    Build and compile a graph that only runs the planner.
    No subagent execution; use for step 1 of refactor.
    """
    builder = StateGraph(PlannerState)
    builder.add_node("planner", create_planner_node())
    builder.set_entry_point("planner")
    builder.add_edge("planner", END)
    return builder.compile()
