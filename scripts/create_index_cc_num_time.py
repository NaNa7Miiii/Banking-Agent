"""
Create composite index on transactions (customer_id_number, transaction_datetime DESC) for PostgreSQL.
Usage (from project root): python -m refactored.scripts.create_index_cc_num_time
Requires .env: DB_HOST, DB_PASSWORD, DB_USERNAME, DB_PORT, DB_DATABASE.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from sqlalchemy import create_engine, text

from refactored.utils.db import get_db_config

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cc_num_time
ON transactions (customer_id_number, transaction_datetime DESC);
"""


def main() -> None:
    cfg = get_db_config()
    url = (
        f"postgresql+psycopg2://{cfg['username']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    )
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(INDEX_SQL))
    print("Index idx_cc_num_time created (or already exists).")


if __name__ == "__main__":
    main()
