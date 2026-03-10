"""
Web search gate: only allow Tavily when the query is about public/policy information.

Responsibility model:
- RAG agent is for policy, product info, definitions, and other public knowledge.
- User-private questions (my transactions, my account, fraud, balance) should be routed
  to SQL agent or Fraud agent; they must NOT trigger web search to avoid PII leakage.

This module uses an LLM (generic role) to classify intent: safe for web (public/policy)
vs private (do not send to Tavily).
"""
import json
from typing import Any

from src.models.llm import get_llm


SYSTEM_PROMPT = """You are a classifier for a banking assistant. Given a user question, decide if it is about PUBLIC/POLICY information (e.g. product terms, policy definitions, general how-to) or about the USER'S OWN DATA (e.g. my transactions, my account, my balance, fraud on my card, suspicious activity).

Rules:
- PUBLIC: general policy, product info, definitions, public knowledge. Safe to answer using web search.
- PRIVATE: anything about the user's own transactions, account, balance, spending, fraud, or personal data. Must NOT use web search; should use SQL or Fraud agents only.

Respond with exactly one JSON object: {"intent": "public"} or {"intent": "private"}. No other text."""


def _parse_intent(raw: str) -> str:
    raw = (raw or "").strip()
    for chunk in raw.split("\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("```"):
            chunk = chunk.replace("```json", "").replace("```", "").strip()
        try:
            obj = json.loads(chunk)
            return (obj.get("intent") or "private").lower()
        except json.JSONDecodeError:
            if "public" in chunk.lower() and "private" not in chunk.lower():
                return "public"
            if "private" in chunk.lower():
                return "private"
    return "private"


def is_safe_for_web_search(question: str) -> bool:
    """
    Return True if the question is about public/policy information and safe to send to external web search.
    Return False if the question is about the user's own data; such questions must not be sent to Tavily.
    Uses LLM (generic role) for classification.
    """
    if not (question or "").strip():
        return False
    try:
        llm = get_llm(role="generic")
        out = llm.chat(system_prompt=SYSTEM_PROMPT, user_prompt=(question or "").strip())
        intent = _parse_intent(out)
        return intent == "public"
    except Exception:
        return False


def web_search_gate_reason(question: str, *, safe: bool | None = None) -> str:
    """
    Human-readable reason for gate decision (for logging or tool response).
    When safe is provided (True/False), uses it and does not call the LLM again.
    When safe is None, calls is_safe_for_web_search(question) to classify.
    """
    if safe is None:
        safe = is_safe_for_web_search(question)
    if safe:
        return "Query is about public/policy info; web search allowed."
    return (
        "Query is about the user's own data (transactions/account/fraud). "
        "Use SQL or Fraud agent; web search is disabled for privacy."
    )
