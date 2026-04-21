"""
Langfuse handler singleton + ContextVar-based propagation across ThreadPoolExecutor workers.

- set_langfuse_handler: called at top of run_task; creates a v4 CallbackHandler and records
  session_id / user_id / trace_name / tags in ContextVars.
- get_langfuse_config: called at every graph.invoke site (main graph + three sub-agents) to
  build a RunnableConfig dict with both the callback and the langfuse_* metadata keys the
  v4 handler parses (langfuse_session_id, langfuse_user_id, langfuse_trace_name, langfuse_tags).
- flush: drain the in-memory event buffer to Langfuse cloud (needed because the SDK is async).

Works across ThreadPoolExecutor because Python's futures executor copies the current
Context (copy_context) when submitting, so ContextVar values set in the main thread
are visible in worker threads.
"""
import os
from contextvars import ContextVar
from typing import Any

_handler_var: ContextVar[Any] = ContextVar("langfuse_handler", default=None)
_session_var: ContextVar[str] = ContextVar("langfuse_session", default="")
_user_var: ContextVar[str] = ContextVar("langfuse_user", default="")
_trace_name_var: ContextVar[str] = ContextVar("langfuse_trace_name", default="")
_tags_var: ContextVar[list] = ContextVar("langfuse_tags", default=[])


def is_enabled() -> bool:
    """Return True only when both keys are present in the environment."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def set_langfuse_handler(
    session_id: str,
    user_id: str,
    trace_name: str | None = None,
    tags: list | None = None,
) -> Any:
    """
    Build a Langfuse v4 CallbackHandler and remember trace attributes in ContextVars.
    Returns None when Langfuse env vars are missing (disables tracing silently).
    """
    if not is_enabled():
        return None
    from langfuse.langchain import CallbackHandler

    handler = CallbackHandler()
    _handler_var.set(handler)
    _session_var.set(session_id or "demo-session")
    _user_var.set(user_id or "demo-user")
    _trace_name_var.set(trace_name or "")
    _tags_var.set(list(tags) if tags is not None else ["banking-agent", "demo"])
    return handler


def get_langfuse_config() -> dict:
    """
    Return a RunnableConfig dict ready to splat into graph.invoke(config=...).
    Contains callbacks + langfuse metadata keys that the v4 handler reads.
    Returns {} when tracing is disabled; {} is a valid no-op config for LangGraph.
    """
    h = _handler_var.get()
    if h is None:
        return {}
    metadata: dict[str, Any] = {
        "langfuse_session_id": _session_var.get(),
        "langfuse_user_id": _user_var.get(),
        "langfuse_tags": _tags_var.get(),
    }
    trace_name = _trace_name_var.get()
    if trace_name:
        metadata["langfuse_trace_name"] = trace_name
    return {"callbacks": [h], "metadata": metadata}


def flush() -> None:
    """Drain pending events to Langfuse cloud. Safe to call when tracing is disabled."""
    if _handler_var.get() is None:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        pass
