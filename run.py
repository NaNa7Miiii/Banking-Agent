"""
Entrypoint: Input+Memory -> Planner (orchestrator planning core) -> Orchestrator loop -> Aggregate -> Memory.
Usage (from project root):
  python -m refactored.run "your question"
  python -m refactored.run "How much did I spend?" [customer_id] [session_id]  # with memory + full execution
Set USE_RUNTIME_GRAPH=1 to use graph-native orchestration (planner -> init -> select -> execute [concurrent wave] -> merge -> evaluate -> aggregate; replan on failure).
"""
import json
import os
import sys
from pathlib import Path

# Ensure project root is on path when run as __main__
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from refactored.graph.main_graph import create_plan_only_graph


def run_task(
    user_input: str,
    customer_id_number: str = "",
    session_id: str = "",
    execute_steps: bool = True,
) -> dict:
    """
    Full task flow: memory enrichment -> planner -> (optional) orchestrator loop -> aggregate -> save memory.
    When execute_steps=True, runs executor for each plan step and returns final_answer; otherwise plan only.
    If USE_RUNTIME_GRAPH=1, uses graph-native runtime with concurrent step execution (ThreadPoolExecutor) and replan.
    """
    prompt_for_planner = user_input
    memory = None

    if customer_id_number and session_id:
        from refactored.utils.memory import (
            create_memory,
            format_conversation_history,
            save_context_and_persist,
        )
        memory = create_memory(customer_id_number, session_id)
        prompt_for_planner = format_conversation_history(
            memory, user_input, max_messages=10, prefix="Previous conversation"
        )

    initial = {
        "user_input": prompt_for_planner,
        "customer_id_number": customer_id_number,
        "session_id": session_id,
        "plan": None,
    }

    use_runtime_graph = os.environ.get("USE_RUNTIME_GRAPH", "").strip().lower() in ("1", "true", "yes")

    if execute_steps and use_runtime_graph:
        from refactored.graph.runtime_graph import create_runtime_graph
        graph = create_runtime_graph()
        result = graph.invoke(initial)
        plan = result.get("plan")
        result["execution_state"] = {
            "plan": plan,
            "step_results": result.get("step_results"),
            "final_answer": result.get("final_answer"),
        } if plan else None
    else:
        graph = create_plan_only_graph()
        result = graph.invoke(initial)
        plan = result.get("plan")
        if execute_steps and plan and (plan.get("steps") or []):
            from refactored.graph.executor import ExecutionContext
            from refactored.graph.orchestrator import run_orchestrator_loop
            context: ExecutionContext = {"current_user_id": customer_id_number or ""}
            final_answer, exec_state = run_orchestrator_loop(plan, user_input, context)
            result["final_answer"] = final_answer
            result["execution_state"] = exec_state
        else:
            result["final_answer"] = None
            result["execution_state"] = None

    if memory and customer_id_number and session_id:
        # Persist the answer we show the user (final_answer if we ran steps, else plan summary)
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


def run_planner(user_input: str, customer_id_number: str = "", session_id: str = "") -> dict:
    """Plan-only: no executor loop. Same as run_task(..., execute_steps=False)."""
    return run_task(user_input, customer_id_number, session_id, execute_steps=False)


def print_plan(plan: dict) -> None:
    """Pretty-print plan for CLI."""
    if not plan:
        print("(No plan generated)")
        return
    print(json.dumps(plan, indent=2, ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m refactored.run <user_input> [customer_id] [session_id]", file=sys.stderr)
        sys.exit(1)
    user_input = sys.argv[1]
    customer_id_number = sys.argv[2] if len(sys.argv) > 2 else ""
    session_id = sys.argv[3] if len(sys.argv) > 3 else ""

    result = run_task(user_input, customer_id_number, session_id, execute_steps=True)
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
