"""
Value retrieval: fetch candidate filter values from DB for the current user.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.utils.db import run_read_only


FILTER_CANDIDATE_COLUMNS = (
    "merchant_category",
    "merchant_name",
    "customer_city",
    "customer_state",
)


def get_candidate_filter_values(
    engine: Engine,
    table_name: str,
    question: str,
    current_user_id: str,
    user_column: str,
    max_distinct: int = 50,
) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    with engine.connect() as conn:
        for col in FILTER_CANDIDATE_COLUMNS:
            try:
                sql = text(
                    f"SELECT DISTINCT {col} FROM {table_name} "
                    f"WHERE {user_column} = :uid AND {col} IS NOT NULL "
                    f"LIMIT :lim"
                )
                rows = conn.execute(
                    sql, {"uid": current_user_id, "lim": max_distinct}
                ).fetchall()
                result[col] = [r[0] for r in rows if r[0] is not None]
            except Exception:
                result[col] = []
    return result


def get_date_range_for_user(
    engine: Engine,
    table_name: str,
    current_user_id: str,
    user_column: str,
    date_column: str = "transaction_datetime",
) -> dict[str, str]:
    sql = (
        f"SELECT MIN({date_column}) AS min_d, MAX({date_column}) AS max_d "
        f"FROM {table_name} WHERE {user_column} = :uid"
    )
    rows = run_read_only(engine, sql, {"uid": current_user_id})
    if not rows or (rows[0].get("min_d") is None and rows[0].get("max_d") is None):
        return {}
    r = rows[0]
    out = {}
    if r.get("min_d") is not None:
        out["min_date"] = str(r["min_d"])[:10]
    if r.get("max_d") is not None:
        out["max_date"] = str(r["max_d"])[:10]
    return out
