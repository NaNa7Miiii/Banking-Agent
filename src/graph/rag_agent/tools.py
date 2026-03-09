"""
RAG agent tools: core helpers (tool_*) and make_rag_tools for LangChain create_agent.
"""
from typing import Any

from langchain_core.tools import tool

from src.graph.rag_agent.utils.query_rewrite import rewrite_query
from src.graph.rag_agent.utils.retrieval import retrieve_with_rerank
from src.graph.rag_agent.utils.tavily_client import tavily_search, extract_contexts_from_tavily


def tool_query_rewrite(question: str) -> str:
    return rewrite_query(question)


def tool_local_retrieve(
    query: str,
    namespace: str,
    filter_dict: dict[str, Any] | None = None,
    top_n: int = 5,
) -> tuple[list[dict], str]:
    chunks = retrieve_with_rerank(
        query, namespace,
        vector_top_k=40,
        rerank_top_n=top_n,
        filter_dict=filter_dict,
    )
    if not chunks:
        return [], "No local documents found for this query."
    lines = []
    for i, c in enumerate(chunks, 1):
        src = c.get("source", "document")
        text = (c.get("text") or "")[:500]
        lines.append(f"[{i}] (Source: {src}) {text}...")
    return chunks, "\n".join(lines)


def tool_web_search(query: str, max_results: int = 3) -> tuple[list[str], str]:
    try:
        raw = tavily_search(query, max_results=max_results)
        contexts, _ = extract_contexts_from_tavily(raw, max_contexts=max_results)
    except Exception as e:
        return [], f"Web search failed: {e}"
    if not contexts:
        return [], "No web results found."
    base = 0  # caller may offset for citation numbering
    lines = [f"[{base + i + 1}] (Source: web) {c[:400]}..." for i, c in enumerate(contexts)]
    return contexts, "\n".join(lines)


def execute_tool(
    tool_name: str,
    tool_input: str,
    namespace: str,
    filter_dict: dict[str, Any] | None = None,
    max_local_chunks: int = 5,
    max_web_contexts: int = 3,
    rewritten_query: str = "",
    use_web_fallback: bool = True,
) -> tuple[str, list[dict], list[str], str]:
    """
    Execute one tool. Returns (observation_str, local_chunks, web_contexts, rewritten_query).
    local_chunks and web_contexts are the new ones from this call; rewritten_query only set for query_rewrite.
    For local_retrieve, if tool_input is empty, uses rewritten_query.
    """
    observation = ""
    local_chunks: list[dict] = []
    web_contexts: list[str] = []
    rewritten = ""

    if tool_name == "query_rewrite":
        rewritten = tool_query_rewrite(tool_input.strip())
        observation = f"Rewritten query: {rewritten}"
    elif tool_name == "local_retrieve":
        q = tool_input.strip() or rewritten_query
        local_chunks, observation = tool_local_retrieve(
            q, namespace, filter_dict=filter_dict, top_n=max_local_chunks
        )
    elif tool_name == "web_search":
        if not use_web_fallback:
            observation = "Web search is disabled."
        else:
            web_contexts, observation = tool_web_search(
                tool_input.strip(), max_results=max_web_contexts
            )
    else:
        observation = f"Unknown tool: {tool_name}"

    return observation, local_chunks, web_contexts, rewritten


def make_rag_tools(
    namespace: str,
    filter_dict: dict[str, Any] | None,
    use_web_fallback: bool,
    max_local_chunks: int,
    max_web_contexts: int,
) -> tuple[list, dict[str, Any]]:
    """Returns (list of LangChain tools, collector dict). Collector: local_chunks, web_contexts, rewritten_query."""
    collector: dict[str, Any] = {
        "local_chunks": [],
        "web_contexts": [],
        "rewritten_query": "",
    }
    f_dict = filter_dict or {}

    @tool
    def query_rewrite(question: str) -> str:
        """Rewrites or expands the user question for better retrieval. Call with the user question or a variant."""
        rewritten = rewrite_query(question)
        collector["rewritten_query"] = rewritten
        return f"Rewritten query: {rewritten}"

    @tool
    def local_retrieve(query: str) -> str:
        """Searches the bank's document index. Input: search query (use rewritten question if you already ran query_rewrite, or the original question)."""
        q = (query or "").strip() or collector.get("rewritten_query", "")
        chunks, obs = tool_local_retrieve(q, namespace, filter_dict=f_dict, top_n=max_local_chunks)
        collector["local_chunks"].extend(chunks)
        return obs

    @tool
    def web_search(query: str) -> str:
        """Searches the web for additional information. Input: search query."""
        if not use_web_fallback:
            return "Web search is disabled."
        contexts, obs = tool_web_search(query, max_results=max_web_contexts)
        collector["web_contexts"].extend(contexts)
        return obs

    return [query_rewrite, local_retrieve, web_search], collector
