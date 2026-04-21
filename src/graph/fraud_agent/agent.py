"""
Fraud agent using LangChain create_agent: tools (get_transactions_via_sql, analyze_risk_scores_batch, query_customer_profile).
Final report: {{FRAUD_TRANSACTION_LIST}} in the LLM output is replaced by the model-predicted high-risk transaction list (variable insertion).
"""
import time
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from src.utils.env import load_env
from src.utils.langfuse_client import get_langfuse_config
from src.graph.fraud_agent.tools import make_fraud_tools
from src.graph.fraud_agent.utils.prompts import agent_system
from src.models.llm import get_create_agent_model_string

load_env()

PLACEHOLDER_FRAUD_LIST = "{{FRAUD_TRANSACTION_LIST}}"


def _build_fraud_list_str(collector: dict[str, Any]) -> str:
    """
    Build the string to insert for {{FRAUD_TRANSACTION_LIST}}: model-predicted high-risk transactions
    from risk_scores.results + full rows from sql_result. If none, return "None".
    """
    risk_scores = collector.get("risk_scores") or {}
    results_list = risk_scores.get("results") or []
    high_risk_ids = {str(r.get("transaction_id") or "") for r in results_list if (r.get("risk_level") or "").strip().lower() == "high"}
    if not high_risk_ids:
        return "None"
    sql_result = collector.get("sql_result") or []
    fraud_rows = [row for row in sql_result if str(row.get("transaction_id") or row.get("trans_num") or "") in high_risk_ids]
    if not fraud_rows:
        return "None"
    lines = []
    for row in fraud_rows:
        lines.append("---")
        for k, v in row.items():
            if v is None:
                lines.append(f"{k}:")
            else:
                s = v.isoformat() if hasattr(v, "isoformat") and callable(getattr(v, "isoformat", None)) else str(v)
                lines.append(f"{k}: {s}")
    return "\n".join(lines)


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

    # Short delay before first LLM call to avoid burst 429 when many cases run in sequence
    time.sleep(0.5)
    graph = create_agent(
        model=get_create_agent_model_string("fraud"),
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
        result = graph.invoke(inputs, config=get_langfuse_config() or None)
        messages = result.get("messages", [])
        analysis = _last_ai_content(messages)
        state["risk_scores"] = collector.get("risk_scores")
        state["profile"] = collector.get("profile")
        state["sql_answer"] = collector.get("sql_answer")
        state["sql_result"] = collector.get("sql_result")
        # Variable insertion: replace placeholder with model-predicted fraud list
        fraud_list_str = _build_fraud_list_str(collector)
        final_analysis = (analysis or "Could not generate analysis report.").replace(PLACEHOLDER_FRAUD_LIST, fraud_list_str)
        state["analysis"] = final_analysis
    except Exception as e:
        state["error"] = str(e)
        state["analysis"] = "Fraud analysis failed; please try again later."
    return state
