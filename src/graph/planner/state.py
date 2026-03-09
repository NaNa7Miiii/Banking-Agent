"""
Graph state for planner agent. State carries user input and plan.
Types align with prompts/planner/output_schema.json.
"""
from typing import TypedDict, List, Optional, Any


# Step dependency (depends_on item)
class StepDependency(TypedDict, total=False):
    step_id: str
    type: str  # "hard" | "soft" | "resource"
    note: Optional[str]


# Write scope for a step (read/write/mixed/none + paths)
class WriteScope(TypedDict):
    mode: str  # "read" | "write" | "mixed" | "none"
    paths: List[str]


# Plan step (matches output_schema.json step item)
class PlanStep(TypedDict, total=False):
    id: str
    title: str
    instruction: str  # Contract for executor: single clear task sentence
    owner: str
    depends_on: List[StepDependency]
    inputs_needed: List[str]
    actions: List[str]
    expected_outputs: List[str]
    acceptance_criteria: List[str]
    fallback: List[str]
    parallel_group: Optional[str]
    write_scope: Optional[WriteScope]
    status: str  # "todo" | "done" | "skipped"


# Join point (merge artifacts from parallel group)
class JoinPoint(TypedDict, total=False):
    after_parallel_group: str
    merge_artifacts_from_steps: List[str]
    into: str
    merge_strategy: str  # "union" | "prefer_latest" | "manual_review" | "llm_refine"


# Subagent directory entry
class SubagentDirectoryEntry(TypedDict):
    name: str
    when_to_use: str


# Full plan (matches output_schema.json)
class Plan(TypedDict, total=False):
    goal: str
    intent_summary: str
    assumptions: List[str]
    constraints: List[str]
    subagent_directory: List[SubagentDirectoryEntry]
    steps: List[PlanStep]
    next_step_id: Optional[str]
    join_points: List[JoinPoint]


class PlannerState(TypedDict, total=False):
    user_input: str
    customer_id_number: str
    session_id: str
    plan: Optional[Plan]
