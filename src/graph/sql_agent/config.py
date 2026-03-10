"""
SQL agent config: table name, row-level column, forbidden columns, LIMIT/row cap.
"""
from src.utils.env import load_env, get_env
from src.utils.db import get_db_config

load_env()

USER_COLUMN = "customer_id_number"
FORBIDDEN_COLUMNS = frozenset({"is_fraud"})

# Default LIMIT injected when SQL has no LIMIT (big-company practice: avoid unbounded SELECT)
DEFAULT_SQL_LIMIT = 1000
# Max rows returned after execution; results beyond this are truncated (safety + performance)
MAX_SQL_ROWS = 1000


def get_default_sql_limit() -> int:
    try:
        return max(1, min(10000, int(get_env("SQL_DEFAULT_LIMIT") or DEFAULT_SQL_LIMIT)))
    except (TypeError, ValueError):
        return DEFAULT_SQL_LIMIT


def get_max_sql_rows() -> int:
    try:
        return max(1, min(10000, int(get_env("SQL_MAX_ROWS") or MAX_SQL_ROWS)))
    except (TypeError, ValueError):
        return MAX_SQL_ROWS


def get_table_name() -> str:
    return get_db_config()["table_name"]
