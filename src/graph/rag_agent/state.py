"""
RAG agent state for ReAct loop. Single source of shape and initial state.
"""
from typing import TypedDict, Any, Optional


class ReActStep(TypedDict, total=False):
    thought: str
    action: str
    action_input: str
    observation: str


class RAGAgentState(TypedDict, total=False):
    question: str
    rewritten_query: str
    namespace: str
    filter_dict: dict[str, Any]
    max_local_chunks: int
    max_web_contexts: int
    steps: list[ReActStep]
    local_chunks: list[dict]
    web_contexts: list[str]
    route_decision: str
    citations: list[dict]
    answer: str
    error: Optional[str]


def initial_rag_state(
    question: str,
    namespace: str,
    filter_dict: dict[str, Any] | None = None,
    max_local_chunks: int = 5,
    max_web_contexts: int = 3,
    rewritten_query: str = "",
) -> RAGAgentState:
    """Build initial RAG state; collector fields filled after run."""
    return {
        "question": question,
        "rewritten_query": rewritten_query,
        "namespace": namespace,
        "filter_dict": filter_dict or {},
        "max_local_chunks": max_local_chunks,
        "max_web_contexts": max_web_contexts,
        "steps": [],
        "local_chunks": [],
        "web_contexts": [],
        "route_decision": "local",
        "citations": [],
        "answer": "",
        "error": None,
    }
