"""
SQL candidate generators: Direct (2 candidates) and Divide-and-Conquer (1 candidate).
"""
import re
from typing import Any

from src.models.llm import get_llm
from src.graph.sql_agent.utils.prompts import (
    system_direct,
    user_direct,
    system_dc,
    user_dc,
)
from src.graph.sql_agent.config import FORBIDDEN_COLUMNS


def _parse_direct_output(raw: str) -> list[str]:
    queries = []
    for line in raw.split("\n"):
        line = line.strip()
        if line.upper().startswith("SQL:"):
            q = line[4:].strip().rstrip(";")
            if q:
                queries.append(q)
    return queries[:2]


def _parse_dc_output(raw: str) -> str | None:
    m = re.search(r"FINAL_SQL:\s*(.+)", raw, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return m.group(1).strip().rstrip(";").strip()


def generate_direct_candidates(
    schema: str,
    question: str,
    value_retrieval: dict[str, Any],
) -> list[str]:
    value_hint = "; ".join(f"{k}={list(v)[:10]}" for k, v in value_retrieval.items() if v)
    llm = get_llm(role="sql", temperature=0.3)
    sys = system_direct(FORBIDDEN_COLUMNS, value_hint or "none")
    user = user_direct(question, schema, value_retrieval)
    raw = llm.chat(system_prompt=sys, user_prompt=user)
    return _parse_direct_output(raw)


def generate_dc_candidate(
    schema: str,
    question: str,
    value_retrieval: dict[str, Any],
) -> str | None:
    llm = get_llm(role="sql", temperature=0.2)
    sys = system_dc(FORBIDDEN_COLUMNS)
    user = user_dc(question, schema, value_retrieval)
    raw = llm.chat(system_prompt=sys, user_prompt=user)
    return _parse_dc_output(raw)
