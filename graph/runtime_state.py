"""
Graph state for the runtime orchestration flow (planner -> init -> select -> execute -> merge -> evaluate -> aggregate; replan path).
Compatible with planner output; holds plan, normalized_steps, step_results, and derived orchestration fields.
"""
from typing import TypedDict, Any, Optional

from refactored.graph.executor.schema import StepResult, ExecutionContext


class RuntimeState(TypedDict, total=False):
    """State for the graph-native orchestration runtime. Planner fills user_input, plan; orchestration nodes fill the rest."""

    # From entry / planner
    user_input: str
    customer_id_number: str
    session_id: str
    plan: Optional[dict[str, Any]]

    # Init orchestration
    execution_context: ExecutionContext
    normalized_steps: list[dict[str, Any]]
    step_results: dict[str, StepResult]

    # Derived (written by select_ready_steps, evaluate_progress, or init reset)
    ready_step_ids: list[str]
    completed_step_ids: list[str]
    failed_step_ids: list[str]

    # Parallel wave: set by select_ready_steps, used by execute (wave) and merge_step_results
    current_parallel_groups: list[str]

    # Evaluate -> aggregate
    should_aggregate: bool
    final_answer: Optional[str]

    # Replan
    replan_count: int
    max_replan: int
    should_replan: bool
    replan_reason: str
