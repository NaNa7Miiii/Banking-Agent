"""
Load RAG agent prompts from prompts/rag_agent. No dependency on src.
"""
from refactored.utils.prompt_loader import load_system_prompt

RAG_MODULE = "rag_agent"


def system_rag() -> str:
    return load_system_prompt(RAG_MODULE, "system_rag.md")


def agent_system() -> str:
    return load_system_prompt(RAG_MODULE, "agent_system.md")


def answer_with_citation(context: str, question: str) -> str:
    t = load_system_prompt(RAG_MODULE, "answer_with_citation.md")
    return t.replace("{{context}}", context).replace("{{question}}", question)
