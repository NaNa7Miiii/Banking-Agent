"""
Task execution state: separate from conversation memory.
Holds current plan, step results, and final answer for one task run.
"""
from typing import TypedDict, Optional, Any


class TaskExecutionState(TypedDict, total=False):
    task_id: str
    user_goal: str
    plan: list[dict[str, Any]]
    step_results: dict[str, Any]  # step_id -> StepResult
    current_step_id: Optional[str]
    replan_count: int
    final_answer: Optional[str]
