"""
SQL agent using LangChain create_agent (tool-calling loop). Preserves same API and return shape.
"""
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from src.utils.env import load_env
from src.utils.db import get_engine
from src.graph.sql_agent.config import get_table_name
from src.graph.sql_agent.tools import make_sql_tools
from src.graph.sql_agent.utils.prompts import agent_system

load_env()

SQL_MODEL = "openai:gpt-4.1"


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


def run_sql_agent_react(
    question: str,
    current_user_id: str,
) -> dict[str, Any]:
    """
    Run SQL agent via LangChain create_agent: tools (get_schema, get_value_constraints,
    propose_sql, execute_sql, fix_sql) in a tool-calling loop; then extract answer and
    sql/result/error from collector.
    """
    engine = get_engine()
    table_name = get_table_name()
    tools, collector = make_sql_tools(
        engine=engine,
        table_name=table_name,
        current_user_id=current_user_id,
        question=question,
    )

    graph = create_agent(
        model=SQL_MODEL,
        tools=tools,
        system_prompt=agent_system(),
    )

    out: dict[str, Any] = {
        "answer": "",
        "sql": None,
        "result": None,
        "error": None,
    }

    try:
        inputs = {"messages": [HumanMessage(content=question)]}
        result = graph.invoke(inputs)
        messages = result.get("messages", [])
        answer = _last_ai_content(messages)
    except Exception as e:
        out["error"] = str(e)
        out["answer"] = "Sorry, an error occurred while answering your question."
        return out

    out["answer"] = answer or "Could not generate an answer."
    out["sql"] = collector.get("sql")
    out["result"] = collector.get("result")
    out["error"] = collector.get("error")

    if not answer and collector.get("error"):
        out["answer"] = "The query could not be executed."

    return out
