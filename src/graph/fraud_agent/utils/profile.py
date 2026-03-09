"""
Customer profile lookup: one efficient SQL over transactions (past 6 months).
- home_city: mode (most frequent city) to avoid "last tx = travel/ fraud" pollution.
- age: from customer_dob (same for user across rows).
- avg_ticket_size, common_categories: aggregated over the same 6-month window.
"""
from typing import Any

from sqlalchemy import text

from src.utils.db import get_engine, get_db_config

USER_COLUMN = "customer_id_number"
PROFILE_WINDOW_MONTHS = 6


def get_customer_profile(cc_num: str) -> dict[str, Any]:
    """
    Return profile for cc_num: age, home_city (mode), avg_ticket_size, common_categories.
    Single round-trip: CTE limits to past 6 months, then one SELECT with scalar subqueries.
    """
    engine = get_engine()
    table = get_db_config()["table_name"]
    out: dict[str, Any] = {
        "age": None,
        "home_city": None,
        "avg_ticket_size": None,
        "common_categories": [],
    }
    sql = text(
        f"""
        WITH user_recent_tx AS (
            SELECT customer_city, customer_dob, transaction_amount, merchant_category
            FROM {table}
            WHERE {USER_COLUMN} = :uid
              AND transaction_datetime >= CURRENT_DATE - INTERVAL '{PROFILE_WINDOW_MONTHS} months'
        )
        SELECT
            (SELECT EXTRACT(YEAR FROM AGE(CURRENT_DATE, MAX(customer_dob)))::INT FROM user_recent_tx) AS age,
            (SELECT ROUND(AVG(transaction_amount), 2) FROM user_recent_tx) AS avg_ticket_size,
            (SELECT customer_city FROM user_recent_tx GROUP BY customer_city ORDER BY COUNT(*) DESC LIMIT 1) AS home_city,
            (SELECT array_agg(merchant_category ORDER BY cnt DESC) FROM (
                SELECT merchant_category, COUNT(*) AS cnt
                FROM user_recent_tx
                WHERE merchant_category IS NOT NULL
                GROUP BY merchant_category
                ORDER BY cnt DESC
                LIMIT 3
            ) sub) AS common_categories
        FROM (SELECT 1) AS _one
        """
    )
    try:
        rows = []
        with engine.connect() as conn:
            rows = conn.execute(sql, {"uid": cc_num}).mappings().fetchall()
        if not rows:
            return out
        r = dict(rows[0])
        if r.get("age") is not None:
            out["age"] = int(r["age"])
        if r.get("avg_ticket_size") is not None:
            out["avg_ticket_size"] = round(float(r["avg_ticket_size"]), 2)
        if r.get("home_city") is not None:
            out["home_city"] = r["home_city"]
        cats = r.get("common_categories")
        if cats is not None:
            out["common_categories"] = list(cats) if hasattr(cats, "__iter__") and not isinstance(cats, str) else []
    except Exception:
        pass
    return out
