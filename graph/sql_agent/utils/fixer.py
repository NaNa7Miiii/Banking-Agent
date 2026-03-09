"""
Query fixer: given failed SQL and error message, return corrected SQL (one attempt).
"""
from refactored.models.llm import get_llm
from refactored.graph.sql_agent.utils.prompts import system_fixer, user_fixer


def query_fixer(
    question: str,
    schema: str,
    failed_sql: str,
    error_msg: str,
) -> str | None:
    llm = get_llm(role="sql", temperature=0.0)
    raw = llm.chat(
        system_prompt=system_fixer(),
        user_prompt=user_fixer(question, schema, failed_sql, error_msg),
    )
    sql = raw.strip().rstrip(";").strip()
    if sql.upper().startswith("SELECT") or sql.upper().startswith("WITH"):
        return sql
    for line in raw.split("\n"):
        line = line.strip()
        if line.upper().startswith("SELECT") or line.upper().startswith("WITH"):
            return line.rstrip(";").strip()
    return None
