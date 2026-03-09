"""
Database connection. Reads from env.
"""
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL

from src.utils.env import load_env, get_env

load_env()


def get_db_config() -> dict[str, Any]:
    host = get_env("DB_HOST")
    password = get_env("DB_PASSWORD")
    if not host:
        raise ValueError("DB_HOST is required")
    if not password:
        raise ValueError("DB_PASSWORD is required")
    return {
        "username": get_env("DB_USERNAME") or "postgres",
        "password": password,
        "host": host,
        "port": int(get_env("DB_PORT") or "5432"),
        "database": get_env("DB_DATABASE") or "customer_transaction_db",
        "table_name": get_env("DB_TABLE_NAME") or "transactions",
    }


def get_engine(echo: bool = False) -> Engine:
    cfg = get_db_config()
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=cfg["username"],
        password=cfg["password"],
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database"],
    )
    return create_engine(url, echo=echo)


def run_read_only(engine: Engine, sql: str, params: dict | None = None) -> list[dict]:
    """Execute a read-only query and return rows as list of dicts."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        rows = result.mappings().fetchall()
    return [dict(r) for r in rows]
