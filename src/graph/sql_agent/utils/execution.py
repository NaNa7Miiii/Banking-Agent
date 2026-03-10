"""
Execute read-only SQL with row-level enforcement, column masking, and LIMIT/row cap.
Big-company practice: (1) inject default LIMIT when missing; (2) cap result set size.
"""
import re
from typing import Any

from sqlalchemy.engine import Engine

from src.utils.db import run_read_only
from src.graph.sql_agent.config import get_default_sql_limit, get_max_sql_rows


READ_ONLY_PATTERN = re.compile(
    r"^\s*(WITH\s+|SELECT\s+)",
    re.IGNORECASE | re.DOTALL,
)
FORBIDDEN_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
# Match LIMIT clause (e.g. LIMIT 100 or LIMIT 10 OFFSET 5)
LIMIT_PATTERN = re.compile(r"\bLIMIT\s+(:\w+|\d+)\b", re.IGNORECASE)


def _normalize_user_filter(sql: str, user_column: str) -> str:
    """Normalize LLM placeholder to SQLAlchemy style: %(uid)s -> :uid, so we can bind uid safely."""
    col = re.escape(user_column)
    sql = re.sub(
        rf"({col}\s*=\s*)%\(uid\)s",
        r"\1:uid",
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def _has_user_filter(sql: str, user_column: str) -> bool:
    """True if SQL already contains a user column = :uid condition (after normalization)."""
    return re.search(rf"{re.escape(user_column)}\s*=\s*:uid", sql, re.IGNORECASE) is not None


def _inject_user_filter(sql: str, user_column: str, current_user_id: str) -> str:
    sql = _normalize_user_filter(sql, user_column)
    if _has_user_filter(sql, user_column):
        return sql.strip().rstrip(";")
    sql_stripped = sql.strip().rstrip(";")
    upper = sql_stripped.upper()
    where_pos = upper.find("WHERE")
    if where_pos >= 0:
        rest_upper = upper[where_pos:]
        insert_before = None
        for sep in ("GROUP BY", "ORDER BY", "LIMIT", "HAVING"):
            idx = rest_upper.find(sep)
            if idx >= 0:
                if insert_before is None or idx < insert_before:
                    insert_before = idx
        if insert_before is not None:
            pos = where_pos + insert_before
            sql_stripped = (
                sql_stripped[:pos] + f" AND {user_column} = :uid " + sql_stripped[pos:]
            )
        else:
            sql_stripped = sql_stripped + f" AND {user_column} = :uid"
    else:
        for sep in ("GROUP BY", "ORDER BY", "LIMIT"):
            if sep in upper:
                idx = upper.index(sep)
                sql_stripped = (
                    sql_stripped[:idx] + f" WHERE {user_column} = :uid " + sql_stripped[idx:]
                )
                break
        else:
            sql_stripped = sql_stripped + f" WHERE {user_column} = :uid"
    return sql_stripped


def _ensure_limit(sql: str, default_limit: int) -> tuple[str, int]:
    """If SQL has no LIMIT clause, append LIMIT :lim. Returns (sql, limit_value)."""
    stripped = sql.strip().rstrip(";")
    if LIMIT_PATTERN.search(stripped):
        return stripped, default_limit  # already has LIMIT; param may still be used for cap
    return stripped + f" LIMIT {default_limit}", default_limit


def execute_read_only_sql(
    engine: Engine,
    sql: str,
    current_user_id: str,
    user_column: str,
    forbidden_columns: frozenset,
) -> tuple[list[dict[str, Any]] | None, str | None, bool]:
    """
    Returns (rows, error_message, truncated). truncated is True when result set hit the row cap.
    """
    if not READ_ONLY_PATTERN.match(sql) or FORBIDDEN_PATTERN.search(sql):
        return None, "Only SELECT queries are allowed.", False
    default_limit = get_default_sql_limit()
    max_rows = get_max_sql_rows()
    try:
        sql_safe = _inject_user_filter(sql, user_column, current_user_id)
        sql_safe, _ = _ensure_limit(sql_safe, default_limit)
        params: dict[str, Any] = {"uid": current_user_id}
        rows = run_read_only(engine, sql_safe, params)
    except Exception as e:
        return None, str(e), False
    out = []
    for i, row in enumerate(rows):
        if i >= max_rows:
            break
        r = {k: v for k, v in row.items() if k not in forbidden_columns}
        out.append(r)
    truncated = len(out) >= max_rows
    return out, None, truncated
