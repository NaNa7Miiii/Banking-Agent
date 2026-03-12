"""
Fixed SQL template for "retrieve user transactions in date range" (e.g. for fraud step).
Ensures all columns required by fraud feature building are returned; used by executor when
the planner's instruction matches this pattern so step2 (fraud) does not fail on missing columns.
"""
import re
from datetime import datetime
from typing import Any

from sqlalchemy.engine import Engine

from src.utils.db import run_read_only
from src.graph.sql_agent.config import USER_COLUMN, get_max_sql_rows

# Columns required for fraud batch scoring (feature build + display)
TRANSACTION_SELECT_COLUMNS = (
    "transaction_id",
    "transaction_datetime",
    "transaction_amount",
    "merchant_name",
    "merchant_category",
    "customer_id_number",
    "customer_dob",
    "customer_gender",
    "customer_city",
    "customer_state",
    "customer_zip",
    "customer_latitude",
    "customer_longitude",
    "customer_city_population",
    "customer_job_title",
    "merchant_latitude",
    "merchant_longitude",
)

# Instruction pattern: retrieve/fetch/get ... transaction(s) ... between X and Y (or from X to Y)
DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# At least two date-like tokens for a range
KEYWORDS_RETRIEVE = ("retrieve", "fetch", "get", "list", "show", "return")
KEYWORDS_TRANSACTION = ("transaction", "transactions")
KEYWORDS_RANGE = ("between", "from", "during", "in the period")


def _parse_date_range(instruction: str) -> tuple[str | None, str | None]:
    """Extract two dates from instruction (start, end). Returns (None, None) if not found."""
    matches = DATE_PATTERN.findall(instruction)
    if len(matches) < 1:
        return None, None
    start = matches[0]
    end = matches[1] if len(matches) >= 2 else matches[0]
    # Validate and normalize
    try:
        d1 = datetime.strptime(start, "%Y-%m-%d")
        d2 = datetime.strptime(end, "%Y-%m-%d")
        if d1 > d2:
            start, end = end, start
        return start, end
    except ValueError:
        return None, None


def _instruction_looks_like_transaction_retrieval(instruction: str) -> bool:
    """True if instruction asks to retrieve user transactions in a date range."""
    lower = instruction.lower()
    has_retrieve = any(k in lower for k in KEYWORDS_RETRIEVE)
    has_tx = any(k in lower for k in KEYWORDS_TRANSACTION)
    has_range = any(k in lower for k in KEYWORDS_RANGE) or DATE_PATTERN.search(instruction)
    return bool(has_retrieve and has_tx and has_range)


def run_transaction_retrieval_template(
    engine: Engine,
    table_name: str,
    current_user_id: str,
    start_date: str,
    end_date: str,
) -> tuple[list[dict[str, Any]] | None, str | None, bool]:
    """
    Execute fixed SELECT for user transactions in [start_date, end_date].
    end_date is inclusive; we use end_date 23:59:59 for the upper bound.
    Returns (rows, error_message, truncated) like execute_read_only_sql.
    """
    try:
        d_s = datetime.strptime(start_date, "%Y-%m-%d")
        d_e = datetime.strptime(end_date, "%Y-%m-%d")
        if d_s > d_e:
            return None, "Invalid date range: start after end.", False
    except ValueError:
        return None, "Invalid date format; use YYYY-MM-DD.", False

    cols = ", ".join(TRANSACTION_SELECT_COLUMNS)
    start_ts = f"{start_date} 00:00:00"
    end_ts = f"{end_date} 23:59:59"
    sql = (
        f"SELECT {cols} FROM {table_name} "
        f"WHERE {USER_COLUMN} = :uid "
        f"AND transaction_datetime >= :start_ts "
        f"AND transaction_datetime <= :end_ts "
        f"ORDER BY transaction_datetime ASC LIMIT 1000"
    )
    params: dict[str, Any] = {
        "uid": current_user_id,
        "start_ts": start_ts,
        "end_ts": end_ts,
    }
    try:
        rows = run_read_only(engine, sql, params)
    except Exception as e:
        return None, str(e), False

    max_rows = get_max_sql_rows()
    out = rows[:max_rows] if len(rows) > max_rows else rows
    truncated = len(rows) > max_rows
    return out, None, truncated
