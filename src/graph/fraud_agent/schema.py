"""
Explicit I/O contract for the Fraud sub-agent.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FraudAgentRequest(BaseModel):
    """Input contract for ``run_fraud_agent``."""

    model_config = ConfigDict(extra="forbid")

    instruction: str
    current_user_id: str = ""
    initial_sql_result: list[dict[str, Any]] | None = Field(
        default=None,
        description="Pre-fetched transaction rows from an upstream SQL step, if any.",
    )
    initial_sql_answer: str | None = None


class FraudAgentResponse(BaseModel):
    """Output contract for ``run_fraud_agent``."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    summary: str = ""
    risk_scores: list[dict[str, Any]] | None = None
    profile: dict[str, Any] | None = None
    error: str | None = None
