"""
Fraud agent using LangChain create_agent: tools (get_transactions_via_sql, analyze_risk_scores_batch, query_customer_profile).
"""
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from src.utils.env import load_env
from src.graph.fraud_agent.tools import make_fraud_tools
from src.graph.fraud_agent.utils.prompts import agent_system

load_env()

FRAUD_MODEL = "openai:gpt-4.1"


def _last_ai_content(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            if (m.content or "").strip() and not getattr(m, "tool_calls", None):
                return (m.content or "").strip()
            continue
        if isinstance(m, dict):
            if m.get("type") == "ai" and m.get("content") and not m.get("tool_calls"):
                return (m.get("content") or "").strip()
    return ""


def run_fraud_agent_react(
    question: str,
    current_user_id: str,
    initial_sql_result: Any = None,
    initial_sql_answer: str | None = None,
) -> dict[str, Any]:
    """
    Run fraud agent: get_transactions_via_sql (calls SQL agent) -> analyze_risk_scores_batch -> optional query_customer_profile -> final analysis.
    If initial_sql_result / initial_sql_answer are provided (e.g. from a previous SQL step in the graph), pre-fill collector so the agent can use "use last result" without re-calling SQL.
    """
    tools, collector = make_fraud_tools(current_user_id=current_user_id)
    if initial_sql_result is not None:
        collector["sql_result"] = initial_sql_result if isinstance(initial_sql_result, list) else list(initial_sql_result) if initial_sql_result else []
        collector["preloaded_from_graph"] = True  # do not overwrite in get_transactions_via_sql
    if initial_sql_answer is not None:
        collector["sql_answer"] = initial_sql_answer

    graph = create_agent(
        model=FRAUD_MODEL,
        tools=tools,
        system_prompt=agent_system(),
    )
    state: dict[str, Any] = {
        "question": question,
        "transaction_input": None,
        "risk_scores": collector.get("risk_scores"),
        "profile": collector.get("profile"),
        "sql_answer": collector.get("sql_answer"),
        "sql_result": collector.get("sql_result"),
        "analysis": "",
        "error": None,
    }
    try:
        inputs = {"messages": [HumanMessage(content=question)]}
        result = graph.invoke(inputs)
        messages = result.get("messages", [])
        analysis = _last_ai_content(messages)
        state["analysis"] = analysis or "Could not generate analysis report."
        state["risk_scores"] = collector.get("risk_scores")
        state["profile"] = collector.get("profile")
        state["sql_answer"] = collector.get("sql_answer")
        state["sql_result"] = collector.get("sql_result")
    except Exception as e:
        state["error"] = str(e)
        state["analysis"] = "Fraud analysis failed; please try again later."
    return state
