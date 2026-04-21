"""
RAG agent: LangChain create_agent with tools (query_rewrite, local_retrieve, web_search).

Public surface:
    * ``invoke(req: RagAgentRequest) -> RagAgentResponse`` — typed contract.
    * ``run_rag_agent(...)`` — legacy dict shape, kept for internal use.
"""
from typing import Any

from src.graph.rag_agent.agent import run_rag_agent_react
from src.graph.rag_agent.schema import RagAgentRequest, RagAgentResponse


def run_rag_agent(
    question: str,
    namespace: str | None = None,
    filter_dict: dict[str, Any] | None = None,
    use_web_fallback: bool = True,
    max_local_chunks: int = 5,
    max_web_contexts: int = 3,
) -> dict[str, Any]:
    """Legacy dict-shaped entry point."""
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


def invoke(req: RagAgentRequest) -> RagAgentResponse:
    """Typed entry point."""
    try:
        raw = run_rag_agent(
            question=req.instruction,
            namespace=req.namespace,
            filter_dict=req.filter_dict,
            use_web_fallback=req.use_web_fallback,
            max_local_chunks=req.max_local_chunks,
            max_web_contexts=req.max_web_contexts,
        )
    except Exception as exc:
        return RagAgentResponse(status="error", error=str(exc))

    error = raw.get("error")
    status = "error" if error else "ok"
    return RagAgentResponse(
        status=status,
        summary=(raw.get("answer") or "").strip() if status == "ok" else "",
        citations=raw.get("citations") or [],
        route_decision=raw.get("route_decision"),
        local_chunks=raw.get("local_chunks") or [],
        web_contexts=raw.get("web_contexts") or [],
        error=error,
    )
