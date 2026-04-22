"""
Explicit I/O contract for the RAG sub-agent.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RagAgentRequest(BaseModel):
    """Input contract for ``run_rag_agent``."""

    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(..., description="The user question to ground in documents.")
    namespace: str | None = None
    filter_dict: dict[str, Any] | None = None
    use_web_fallback: bool = True
    max_local_chunks: int = Field(5, ge=1, le=20)
    max_web_contexts: int = Field(3, ge=0, le=10)


class RagAgentResponse(BaseModel):
    """Output contract for ``run_rag_agent``."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    summary: str = ""
    # Items are JSON-compatible but not all tools return the same shape:
    #   - local_chunks: usually {text, score, metadata} dicts from Pinecone
    #   - web_contexts: Tavily tool returns plain strings like "Source: ... \n ..."
    #   - citations: a list of URL/title dicts, but some paths emit plain strings
    # We keep the contract lenient (Any) at the field level and document the
    # expected shape here so downstream consumers can branch on type.
    citations: list[Any] = Field(default_factory=list)
    route_decision: str | None = None
    local_chunks: list[Any] = Field(default_factory=list)
    web_contexts: list[Any] = Field(default_factory=list)
    error: str | None = None
