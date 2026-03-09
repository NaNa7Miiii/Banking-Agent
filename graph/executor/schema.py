"""
Unified types for the executor layer. StepResult uses summary + artifacts; ExecutionContext is explicit.
"""
from typing import TypedDict, Any, Optional


class StepResult(TypedDict, total=False):
    step_id: str
    owner: str
    status: str  # "ok" | "error"
    data: dict[str, Any]  # { "summary": str, "artifacts": dict }
    error_message: str
    metadata: dict[str, Any]  # e.g. agent, timestamp, used_tools


class ExecutionContext(TypedDict, total=False):
    """Explicit context for executor. current_user_id required for sql_agent and fraud_agent."""
    current_user_id: str
    namespace: Optional[str]
    filter_dict: Optional[dict[str, Any]]
    memory_summary: Optional[str]
    previous_step_results: Optional[dict[str, Any]]
