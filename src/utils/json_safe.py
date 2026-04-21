"""
Utility to coerce DB rows / nested structures into JSON-serializable primitives.

We normalize at the sub-agent boundary so that every Request/Response on the
wire is plain JSON; no `datetime`, `Decimal`, `UUID`, `bytes`, etc. leak out.
"""
from __future__ import annotations

import base64
import datetime as _dt
from decimal import Decimal
from typing import Any
from uuid import UUID


def to_json_safe(value: Any) -> Any:
    """Recursively convert ``value`` into JSON-serializable primitives.

    - ``datetime`` / ``date`` / ``time`` -> ISO 8601 string
    - ``Decimal`` -> ``float`` (good enough for display/LLM reasoning)
    - ``UUID`` -> ``str``
    - ``bytes`` -> base64 ASCII string
    - ``set`` / ``tuple`` -> ``list``
    - dict keys are coerced to ``str``
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(v) for v in value]
    # Fallback: stringify unknown objects rather than raising at serialization time.
    return str(value)


def rows_to_json_safe(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Normalize a list of DB-row dicts in one shot."""
    if rows is None:
        return None
    return [to_json_safe(r) for r in rows]
