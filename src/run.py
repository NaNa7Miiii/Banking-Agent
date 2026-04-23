"""
Entrypoint: Input+Memory -> Runtime graph (planner -> init -> select -> execute -> merge -> evaluate -> aggregate) -> Memory.
Usage (from project root):
  python -m src.run "your question"
  python -m src.run "How much did I spend?" [customer_id] [session_id]  # with memory

Also exposes ``run_task_stream`` — a generator version used by the SSE chat endpoint
to emit progress events (planning, step completion, final answer) as the graph runs.
"""
import json
import logging
import sys
import time
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# Ensure project root is on path when run as __main__
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.graph.runtime_graph import create_runtime_graph
from src.utils.env import load_env
from src.utils.langfuse_client import (
    set_langfuse_handler,
    get_langfuse_config,
    flush as langfuse_flush,
)

load_env()


def run_task(
    user_input: str,
    customer_id_number: str = "",
    session_id: str = "",
) -> dict:
    """
    Full task flow: memory enrichment -> runtime graph (plan + orchestration + subagent execution) -> save memory.
    """
    prompt_for_planner = user_input
    memory = None

    if customer_id_number and session_id:
        try:
            from src.utils.memory import (
                create_memory,
                format_conversation_history,
                save_context_and_persist,
            )
            memory = create_memory(customer_id_number, session_id)
            prompt_for_planner = format_conversation_history(
                memory, user_input, max_messages=10, prefix="Previous conversation"
            )
        except Exception as e:
            logger.warning(
                "Memory unavailable (e.g. Redis down): %s. Proceeding without conversation history.",
                e,
                exc_info=True,
            )
            memory = None
            prompt_for_planner = user_input

    initial = {
        "user_input": prompt_for_planner,
        "customer_id_number": customer_id_number,
        "session_id": session_id,
        "plan": None,
    }

    set_langfuse_handler(
        session_id=session_id or "demo-session",
        user_id=customer_id_number or "demo-user",
        trace_name=f"banking-query: {user_input[:60]}",
    )

    graph = create_runtime_graph()
    invoke_config: dict = {"recursion_limit": 100}
    invoke_config.update(get_langfuse_config())
    result = graph.invoke(initial, config=invoke_config)
    langfuse_flush()
    plan = result.get("plan")
    result["execution_state"] = {
        "plan": plan,
        "step_results": result.get("step_results"),
        "final_answer": result.get("final_answer"),
    } if plan else None

    if memory and customer_id_number and session_id:
        if result.get("final_answer"):
            to_save = result["final_answer"]
        elif plan:
            goal = plan.get("goal") or "N/A"
            steps = plan.get("steps") or []
            to_save = f"Plan: {goal} ({len(steps)} steps)."
        else:
            to_save = "No plan or result generated."
        save_context_and_persist(
            memory, customer_id_number, session_id, user_input, to_save
        )

    return result


_NODE_LABELS = {
    "planner": "Planning…",
    "init_orchestration": "Preparing steps…",
    "select_ready_steps": "Selecting next step…",
    "execute_ready_steps": "Running sub-agents…",
    "merge_step_results": "Merging results…",
    "evaluate_progress": "Checking progress…",
    "maybe_replan": "Refining plan…",
    "aggregate": "Writing answer…",
}
_OWNER_LABELS = {
    "subagent:sql": "SQL agent",
    "subagent:rag": "Knowledge base",
    "subagent:fraud": "Fraud detection",
}


def run_task_stream(
    user_input: str,
    customer_id_number: str = "",
    session_id: str = "",
) -> Iterator[dict]:
    """
    Generator counterpart of :func:`run_task`. Yields progress events as the runtime
    graph advances, so a client (e.g. SSE endpoint) can show live status while the
    agent plans, dispatches sub-agents, and aggregates the final answer.

    Event shapes (all JSON-serializable):
      * ``{"type": "status",     "label": str}``
      * ``{"type": "plan",       "plan": {...}}``
      * ``{"type": "step_done",  "step_id": str, "owner": str|None,
                                 "owner_label": str, "status": "ok"|"error"}``
      * ``{"type": "final",      "final_answer": str|None, "plan": {...},
                                 "step_results": {...}, "latency_ms": int}``
      * ``{"type": "error",      "error": str, "latency_ms": int}``

    Memory semantics match :func:`run_task`: conversation history is loaded from Redis
    if both ``customer_id_number`` and ``session_id`` are provided, and the final answer
    is persisted back on success.
    """
    t0 = time.perf_counter()
    prompt_for_planner = user_input
    memory = None

    if customer_id_number and session_id:
        try:
            from src.utils.memory import (
                create_memory,
                format_conversation_history,
            )
            memory = create_memory(customer_id_number, session_id)
            prompt_for_planner = format_conversation_history(
                memory, user_input, max_messages=10, prefix="Previous conversation"
            )
        except Exception as e:
            logger.warning(
                "Memory unavailable (e.g. Redis down): %s. Proceeding without history.",
                e,
                exc_info=True,
            )
            memory = None
            prompt_for_planner = user_input

    initial = {
        "user_input": prompt_for_planner,
        "customer_id_number": customer_id_number,
        "session_id": session_id,
        "plan": None,
    }

    set_langfuse_handler(
        session_id=session_id or "demo-session",
        user_id=customer_id_number or "demo-user",
        trace_name=f"banking-query: {user_input[:60]}",
    )

    graph = create_runtime_graph()
    invoke_config: dict = {"recursion_limit": 100}
    invoke_config.update(get_langfuse_config())

    final_state: dict = dict(initial)
    seen_step_ids: set[str] = set()

    # Kick off with an immediate status so the UI doesn't show a blank "Thinking…".
    yield {"type": "status", "label": "Planning…"}

    try:
        for update in graph.stream(initial, config=invoke_config, stream_mode="updates"):
            # ``update`` is a dict ``{node_name: partial_state_delta}`` per super-step.
            for node_name, delta in (update or {}).items():
                if node_name in ("__start__", "__end__"):
                    continue
                if isinstance(delta, dict):
                    # Accumulate so ``final_state`` holds the terminal state after the loop.
                    final_state.update(delta)

                if node_name == "planner" and isinstance(delta, dict) and delta.get("plan"):
                    plan = delta["plan"]
                    yield {"type": "plan", "plan": plan}
                    owners = [s.get("owner") for s in (plan.get("steps") or []) if s.get("owner")]
                    if owners:
                        pretty = " · ".join(_OWNER_LABELS.get(o, o) for o in owners)
                        yield {"type": "status", "label": f"Plan ready · {pretty}"}
                        continue

                if node_name == "execute_ready_steps":
                    step_results = final_state.get("step_results") or {}
                    plan_steps_by_id = {
                        s.get("id"): s
                        for s in ((final_state.get("plan") or {}).get("steps") or [])
                    }
                    newly_done = [sid for sid in step_results if sid not in seen_step_ids]
                    for sid in newly_done:
                        res = step_results.get(sid) or {}
                        owner = (plan_steps_by_id.get(sid) or {}).get("owner")
                        yield {
                            "type": "step_done",
                            "step_id": sid,
                            "owner": owner,
                            "owner_label": _OWNER_LABELS.get(owner, owner or sid),
                            "status": res.get("status", "ok"),
                        }
                        seen_step_ids.add(sid)
                    total = len(plan_steps_by_id) or len(seen_step_ids)
                    if total:
                        yield {
                            "type": "status",
                            "label": f"{len(seen_step_ids)}/{total} steps complete",
                        }
                    continue

                label = _NODE_LABELS.get(node_name)
                if label:
                    yield {"type": "status", "label": label}
    except Exception as exc:
        logger.exception("run_task_stream: graph raised")
        yield {
            "type": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        }
        try:
            langfuse_flush()
        except Exception:
            pass
        return

    try:
        langfuse_flush()
    except Exception:
        pass

    final_answer = final_state.get("final_answer")

    if memory and customer_id_number and session_id:
        try:
            from src.utils.memory import save_context_and_persist
            if final_answer:
                to_save = final_answer
            elif final_state.get("plan"):
                plan = final_state["plan"]
                goal = plan.get("goal") or "N/A"
                steps = plan.get("steps") or []
                to_save = f"Plan: {goal} ({len(steps)} steps)."
            else:
                to_save = "No plan or result generated."
            save_context_and_persist(
                memory, customer_id_number, session_id, user_input, to_save
            )
        except Exception as e:
            logger.warning("Memory save failed: %s", e, exc_info=True)

    yield {
        "type": "final",
        "final_answer": final_answer,
        "plan": final_state.get("plan"),
        "step_results": final_state.get("step_results"),
        "latency_ms": int((time.perf_counter() - t0) * 1000),
    }


def print_plan(plan: dict) -> None:
    """Pretty-print plan for CLI."""
    if not plan:
        print("(No plan generated)")
        return
    print(json.dumps(plan, indent=2, ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.run <user_input> [customer_id] [session_id]", file=sys.stderr)
        sys.exit(1)
    user_input = sys.argv[1]
    customer_id_number = sys.argv[2] if len(sys.argv) > 2 else ""
    session_id = sys.argv[3] if len(sys.argv) > 3 else ""

    result = run_task(user_input, customer_id_number, session_id)
    plan = result.get("plan")
    final_answer = result.get("final_answer")

    print("--- Plan ---")
    print_plan(plan)
    if final_answer is not None:
        print("--- Final answer ---")
        print(final_answer)
    print("--- End ---")


if __name__ == "__main__":
    main()
