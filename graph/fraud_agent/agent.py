"""
Fraud agent using LangChain create_agent: tools (get_transactions_via_sql, analyze_risk_scores_batch, query_customer_profile).
"""
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from refactored.utils.env import load_env
from refactored.graph.fraud_agent.tools import make_fraud_tools
from refactored.graph.fraud_agent.utils.prompts import agent_system

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
    if initial_sql_answer is not None:
        collector["sql_answer"] = initial_sql_answer

    system_prompt = agent_system()
    if initial_sql_result and len(collector.get("sql_result") or []) > 0:
        system_prompt += (
            "\n\n## Pre-loaded data (IMPORTANT)\n"
            "Transaction data is ALREADY loaded from a previous step. You MUST call **analyze_risk_scores_batch** with the exact input: **use last result** (nothing else). Do NOT call get_transactions_via_sql. Do NOT say that no data is loaded or ask to fetch. Call the tool first, then write the report from its output."
        )
        question = "Run risk analysis on the pre-loaded transactions and provide the risk report. Call analyze_risk_scores_batch with input: use last result."

    graph = create_agent(
        model=FRAUD_MODEL,
        tools=tools,
        system_prompt=system_prompt,
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

        # Fallback: if we had pre-loaded data but the agent replied without using it, run scoring directly
        preloaded = initial_sql_result and len(collector.get("sql_result") or []) > 0
        if preloaded and state["risk_scores"] is None:
            low = (state["analysis"] or "").lower()
            if "no transaction data" in low or "need to fetch" in low or "would you like me to fetch" in low or "first retrieve" in low:
                from refactored.graph.fraud_agent.utils.batch_inference import run_batch_risk_scores
                data = collector.get("sql_result") or []
                if data:
                    state["risk_scores"] = run_batch_risk_scores(data)
                    summary = (state["risk_scores"] or {}).get("summary") or ""
                    state["analysis"] = f"Risk Analysis Report (from pre-loaded data):\n\n{summary}"
    except Exception as e:
        state["error"] = str(e)
        state["analysis"] = "Fraud analysis failed; please try again later."
    return state
