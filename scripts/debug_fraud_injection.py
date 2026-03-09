#!/usr/bin/env python3
"""
Debug: after runtime graph run, check whether step1 result is in step_results
and whether step2's depends_on would let _run_fraud extract initial_sql_result.
Run from project root: USE_RUNTIME_GRAPH=1 python refactored/scripts/debug_fraud_injection.py
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

os.environ["USE_RUNTIME_GRAPH"] = "1"

def main():
    from refactored.graph.runtime_graph import create_runtime_graph

    initial = {
        "user_input": "Do I have any suspicious transactions in 2020-12?",
        "customer_id_number": os.getenv("TEST_CUSTOMER_ID", "2242180000000000.0"),
        "session_id": "",
        "plan": None,
    }
    graph = create_runtime_graph()
    result = graph.invoke(initial)

    step_results = result.get("step_results") or {}
    plan = result.get("plan") or {}
    steps = plan.get("steps") or []

    print("=== step_results keys ===")
    print(list(step_results.keys()))

    for sid, sr in step_results.items():
        print(f"\n=== step_results[{sid!r}] (keys) ===")
        print(list(sr.keys()) if isinstance(sr, dict) else type(sr))
        if isinstance(sr, dict):
            data = sr.get("data") or {}
            arts = data.get("artifacts") or {}
            print(f"  data.artifacts keys: {list(arts.keys())}")
            if "result" in arts:
                r = arts["result"]
                print(f"  data.artifacts.result type: {type(r)}, len: {len(r) if r is not None else 'N/A'}")
                if isinstance(r, list) and len(r) > 0:
                    print(f"  first row keys: {list(r[0].keys()) if isinstance(r[0], dict) else type(r[0])}")
            else:
                print("  data.artifacts.result: MISSING")

    print("\n=== plan.steps (id, depends_on) ===")
    for s in steps:
        dep = s.get("depends_on") or []
        print(f"  id={s.get('id')!r}, depends_on={dep}")

    # Simulate _run_fraud extraction for step2
    step2 = next((s for s in steps if (s.get("id") or "") != "step1" and "fraud" in (s.get("owner") or "").lower()), None)
    if not step2:
        step2 = steps[1] if len(steps) > 1 else None
    if step2:
        prev_results = step_results
        dep_id_candidates = []
        for dep in (step2.get("depends_on") or []):
            dep_id = (dep.get("step_id") or "").strip() if isinstance(dep, dict) else str(dep).strip()
            dep_id_candidates.append(dep_id)
        print(f"\n=== Simulated _run_fraud for step2 id={step2.get('id')!r} ===")
        print(f"  depends_on step_id(s): {dep_id_candidates}")
        print(f"  prev_results keys: {list(prev_results.keys())}")
        for dep_id in dep_id_candidates:
            if not dep_id:
                continue
            sr = prev_results.get(dep_id) or {}
            print(f"  prev_results[{dep_id!r}]: status={sr.get('status')!r}")
            data = sr.get("data") or {}
            artifacts = data.get("artifacts") or {}
            has_result = "result" in artifacts and artifacts["result"] is not None
            print(f"    data.artifacts.result present: {has_result}")
            if has_result:
                print(f"    len(artifacts['result']): {len(artifacts['result'])}")
                break

if __name__ == "__main__":
    main()
