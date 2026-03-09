"""
Load SQL agent prompts from prompts/sql_agent/*.md and format with variables.
Design matches prompts/planner: one .md per system prompt.
"""
from src.utils.prompt_loader import load_system_prompt

SQL_AGENT_MODULE = "sql_agent"


def system_direct(forbidden_columns: frozenset, value_hint: str) -> str:
    t = load_system_prompt(SQL_AGENT_MODULE, "system_direct.md")
    return t.replace("{{forbidden_columns}}", ", ".join(sorted(forbidden_columns))).replace(
        "{{value_hint}}", value_hint or "none"
    )


def user_direct(question: str, schema: str, value_retrieval: dict) -> str:
    value_hint = "; ".join(f"{k}={v}" for k, v in value_retrieval.items() if v)
    return f"""Schema:
{schema}

Candidate filter values: {value_hint or "none"}

Question: {question}

Generate 2 SQL queries, each line: SQL: <query>"""


def system_dc(forbidden_columns: frozenset) -> str:
    t = load_system_prompt(SQL_AGENT_MODULE, "system_dc.md")
    return t.replace("{{forbidden_columns}}", ", ".join(sorted(forbidden_columns)))


def user_dc(question: str, schema: str, value_retrieval: dict) -> str:
    value_hint = "; ".join(f"{k}={v}" for k, v in value_retrieval.items() if v)
    return f"""Schema:
{schema}

Candidate values: {value_hint or "none"}

Question: {question}

Reasoning then one line: FINAL_SQL: <query>"""


def system_pairwise() -> str:
    return load_system_prompt(SQL_AGENT_MODULE, "system_pairwise.md")


def user_pairwise(question: str, schema: str, sql_a: str, sql_b: str) -> str:
    return f"""Schema: {schema}

Question: {question}

Candidate A: {sql_a}

Candidate B: {sql_b}

Which is better? Reply A or B only."""


def system_fixer() -> str:
    return load_system_prompt(SQL_AGENT_MODULE, "system_fixer.md")


def user_fixer(question: str, schema: str, failed_sql: str, error_msg: str) -> str:
    return f"""Schema: {schema}

Question: {question}

Failed SQL: {failed_sql}

Error: {error_msg}

Corrected SQL (only the query):"""


def system_answer() -> str:
    return load_system_prompt(SQL_AGENT_MODULE, "system_answer.md")


def agent_system() -> str:
    return load_system_prompt(SQL_AGENT_MODULE, "agent_system.md")


def user_answer(question: str, result_json: str) -> str:
    return f"Question: {question}\n\nResult:\n{result_json}"
