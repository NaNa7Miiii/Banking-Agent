"""
Get table schema for SQL generation. Excludes forbidden columns (e.g. is_fraud) from user-facing schema.
"""
from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def format_column(col: dict, table_name: str) -> str:
    name = col["name"]
    typ = str(col["type"])
    nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
    return f"  {name} {typ} {nullable}"


def get_schema(
    engine: Engine,
    table_name: str,
    exclude_columns: frozenset | None = None,
) -> str:
    """
    Return user-facing schema as a string. Columns in exclude_columns are omitted.
    """
    exclude = exclude_columns or frozenset()
    inspector = inspect(engine)
    cols = inspector.get_columns(table_name)
    lines = [f"Table: {table_name}", "-" * (7 + len(table_name))]
    for c in cols:
        if c["name"] in exclude:
            continue
        lines.append(format_column(c, table_name))
    return "\n".join(lines)
