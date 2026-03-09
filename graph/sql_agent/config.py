"""
SQL agent config: table name, row-level column, forbidden columns. No dependency on src.
"""
from refactored.utils.db import get_db_config

USER_COLUMN = "customer_id_number"
FORBIDDEN_COLUMNS = frozenset({"is_fraud"})


def get_table_name() -> str:
    return get_db_config()["table_name"]
