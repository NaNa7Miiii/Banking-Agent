"""
RAG agent using LangChain create_agent (tool-calling loop). Preserves same API and return shape.
"""
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from src.utils.env import load_env
from src.graph.rag_agent.state import RAGAgentState, initial_rag_state
from src.graph.rag_agent.config import get_default_namespace
from src.graph.rag_agent.tools import make_rag_tools
from src.graph.rag_agent.utils.prompts import agent_system
from src.graph.rag_agent.utils.web_search_gate import is_safe_for_web_search
from src.models.llm import get_create_agent_model_string

load_env()

NO_CONTEXT_MESSAGE = (
    "I could not find sufficient information in the provided documents to answer this. "
    "Please rephrase your question or specify which document type you mean."
)


def _last_ai_content(messages: list) -> str:
    """Extract the final answer from the last AI message that has content and no tool_calls."""
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            if (m.content or "").strip() and not getattr(m, "tool_calls", None):
                return (m.content or "").strip()
            continue
        if isinstance(m, dict):
            if m.get("type") == "ai" and m.get("content") and not m.get("tool_calls"):
                return (m.get("content") or "").strip()
    return ""


def run_rag_agent_react(
    question: str,
    namespace: str | None = None,
    filter_dict: dict[str, Any] | None = None,
    use_web_fallback: bool = True,
    max_local_chunks: int = 5,
    max_web_contexts: int = 3,
) -> RAGAgentState:
    """
    Run RAG via LangChain create_agent: tools (query_rewrite, local_retrieve, web_search)
    in a tool-calling loop; then extract answer and build citations from collector.

    Web search (Tavily) is only used for public/policy queries. User-private questions
    (my transactions, account, fraud) are gated: no web search, to avoid PII leakage;
    those should be routed to SQL agent or Fraud agent.
    """
    ns = namespace or get_default_namespace()
    # Gate: allow web only when question is about public/policy info; private -> SQL/Fraud, no web
    web_allowed = use_web_fallback and is_safe_for_web_search(question)
    tools, collector = make_rag_tools(
        namespace=ns,
        filter_dict=filter_dict,
        use_web_fallback=web_allowed,
        max_local_chunks=max_local_chunks,
        max_web_contexts=max_web_contexts,
    )

    graph = create_agent(
        model=get_create_agent_model_string("rag"),
        tools=tools,
        system_prompt=agent_system(),
    )

    state = initial_rag_state(
        question=question,
        namespace=ns,
        filter_dict=filter_dict,
        max_local_chunks=max_local_chunks,
        max_web_contexts=max_web_contexts,
        rewritten_query=collector.get("rewritten_query", ""),
    )

    try:
        inputs = {"messages": [HumanMessage(content=question)]}
        result = graph.invoke(inputs)
        messages = result.get("messages", [])
        answer = _last_ai_content(messages)
    except Exception as e:
        state["error"] = str(e)
        state["answer"] = "Sorry, an error occurred while generating the answer."
        return state

    local_chunks = collector.get("local_chunks") or []
    web_contexts = collector.get("web_contexts") or []
    state["rewritten_query"] = collector.get("rewritten_query", "")
    state["local_chunks"] = local_chunks
    state["web_contexts"] = web_contexts
    state["answer"] = answer if answer else NO_CONTEXT_MESSAGE

    # Build citations
    citations = []
    for i, c in enumerate(local_chunks, 1):
        citations.append({"index": i, "source": c.get("source", "document"), "text": (c.get("text") or "")[:200]})
    base = len(local_chunks) + 1
    for j, w in enumerate(web_contexts):
        citations.append({"index": base + j, "source": "web", "text": (w or "")[:200]})
    state["citations"] = citations

    if local_chunks:
        state["route_decision"] = "both" if web_contexts else "local"
    elif web_contexts:
        state["route_decision"] = "web"
    else:
        state["route_decision"] = "refuse"

    return state
