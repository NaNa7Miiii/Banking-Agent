"""
RAG agent: LangChain create_agent with tools (query_rewrite, local_retrieve, web_search).
"""
from typing import Any

from src.graph.rag_agent.agent import run_rag_agent_react


def run_rag_agent(
    question: str,
    namespace: str | None = None,
    filter_dict: dict[str, Any] | None = None,
    use_web_fallback: bool = True,
    max_local_chunks: int = 5,
    max_web_contexts: int = 3,
) -> dict[str, Any]:
    """
    Run the RAG agent (LangChain create_agent) and return:
    answer, citations, route_decision, local_chunks, web_contexts, error.
    """
    state = run_rag_agent_react(
        question=question,
        namespace=namespace,
        filter_dict=filter_dict,
        use_web_fallback=use_web_fallback,
        max_local_chunks=max_local_chunks,
        max_web_contexts=max_web_contexts,
    )
    return {
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
        "route_decision": state.get("route_decision", "refuse"),
        "local_chunks": state.get("local_chunks", []),
        "web_contexts": state.get("web_contexts", []),
        "error": state.get("error"),
    }
