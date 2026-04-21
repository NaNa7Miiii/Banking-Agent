"""
Explicit I/O contract for the SQL sub-agent.

Every field is JSON-serializable so the contract is transport-agnostic: the same
schema describes an in-process call today and an HTTP/gRPC call tomorrow.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SqlAgentRequest(BaseModel):
    """Input contract for ``run_sql_agent``."""

    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(..., description="Natural-language instruction to turn into SQL.")
    current_user_id: str = Field("", description="Row-level security: scope all queries to this user.")
    max_fix_attempts: int = Field(2, ge=0, le=5)


class SqlAgentResponse(BaseModel):
    """Output contract for ``run_sql_agent``."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    summary: str = ""
    sql: str | None = None
    result: list[dict[str, Any]] | None = None
    row_count: int | None = None
    truncated: bool = False
    error: str | None = None
