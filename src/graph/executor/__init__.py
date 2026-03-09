"""
Executor layer: single entry execute_step(step, context) -> StepResult.
Routes to sql_agent, rag_agent, fraud_agent and normalizes returns.
Owner canonicalization and registry live in router.py.
"""
from src.graph.executor.schema import StepResult, ExecutionContext
from src.graph.executor.executor import execute_step
from src.graph.executor.router import get_canonical, supported_owners

__all__ = [
    "StepResult",
    "ExecutionContext",
    "execute_step",
    "get_canonical",
    "supported_owners",
]
