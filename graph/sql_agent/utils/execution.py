"""
Execute read-only SQL with row-level enforcement and column masking.
"""
import re
from typing import Any

from sqlalchemy.engine import Engine

from refactored.utils.db import run_read_only


READ_ONLY_PATTERN = re.compile(
    r"^\s*(WITH\s+|SELECT\s+)",
    re.IGNORECASE | re.DOTALL,
)
FORBIDDEN_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


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


def execute_read_only_sql(
    engine: Engine,
    sql: str,
    current_user_id: str,
    user_column: str,
    forbidden_columns: frozenset,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not READ_ONLY_PATTERN.match(sql) or FORBIDDEN_PATTERN.search(sql):
        return None, "Only SELECT queries are allowed."
    try:
        sql_safe = _inject_user_filter(sql, user_column, current_user_id)
        params: dict[str, Any] = {"uid": current_user_id}
        rows = run_read_only(engine, sql_safe, params)
    except Exception as e:
        return None, str(e)
    out = []
    for row in rows:
        r = {k: v for k, v in row.items() if k not in forbidden_columns}
        out.append(r)
    return out, None
