"""
Executor layer: single entry execute_step(step, context) -> StepResult.
Routes to sql_agent, rag_agent, fraud_agent and normalizes returns.
Owner canonicalization and registry live in router.py.
"""
from refactored.graph.executor.schema import StepResult, ExecutionContext
from refactored.graph.executor.executor import execute_step
from refactored.graph.executor.router import get_canonical, supported_owners

__all__ = [
    "StepResult",
    "ExecutionContext",
    "execute_step",
    "get_canonical",
    "supported_owners",
]
