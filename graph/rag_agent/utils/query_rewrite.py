"""
Query rewrite/expansion for better retrieval. Uses LLM to expand abbreviations and synonyms.
"""
from refactored.models.llm import get_llm
from refactored.utils.prompt_loader import load_system_prompt

RAG_MODULE = "rag_agent"


def rewrite_query(question: str) -> str:
    """Rewrite the user question for better retrieval (LLM-based expansion/cleanup)."""
    q = (question or "").strip()
    if not q:
        return q
    try:
        system = load_system_prompt(RAG_MODULE, "query_rewrite.md")
        llm = get_llm(role="rag", temperature=0.0)
        rewritten = llm.chat(system_prompt=system, user_prompt=q)
        out = (rewritten or "").strip()
        return out if out else q
    except Exception:
        return q
