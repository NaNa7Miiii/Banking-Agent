"""
Owner canonicalization and routing registry. Keeps ROUTER and aliases in one place for clarity and extension.
Executor registers handlers here; only canonical owner keys are used.
"""
from typing import Any, Callable

# Canonical format: subagent:<name>. All downstream (executor, orchestrator, trace) use this.
OWNER_ALIASES: dict[str, str] = {
    "sql_agent": "subagent:sql",
    "rag_agent": "subagent:rag",
    "fraud_agent": "subagent:fraud",
}

# Handlers register with canonical owner only. Type: (step, context) -> StepResult.
ROUTER: dict[str, Callable[[Any, Any], Any]] = {}


def get_canonical(owner: str) -> str:
    """Normalize owner to canonical form (subagent:sql, subagent:rag, subagent:fraud)."""
    key = (owner or "").strip().lower()
    return OWNER_ALIASES.get(key, (owner or "").strip())


def register(owner: str, handler: Callable[[Any, Any], Any]) -> None:
    """Register a handler for a canonical owner. Idempotent: repeated register for same owner overwrites; safe if module is re-imported."""
    ROUTER[owner] = handler


def supported_owners() -> list[str]:
    """Return sorted list of supported owner strings (for error messages)."""
    return sorted(ROUTER.keys())
