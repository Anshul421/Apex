from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict):
    """
    Complete state carried by one LangGraph reconciliation thread.

    All keys are required intentionally. The orchestrator seeds every key in
    ``initial_state`` and LangGraph nodes return *partial updates* that are
    merged into that state. Keeping the state total avoids unsafe TypedDict
    indexing warnings in Pylance while preserving incremental node updates.
    """

    # Identity / execution
    run_id: str
    athlete_id: str
    reason: str
    current_reason: str
    attempt: int
    status: str
    error: str | None

    # Authoritative world snapshot, serialized for checkpoint safety
    world: dict[str, Any]
    world_state_hash: str

    # Plan lineage
    parent_plan_id: str | None
    plan_id: str | None
    plan_version: int | None
    diff: dict[str, Any]

    # Deterministic planning state
    intent: dict[str, Any]
    candidates: dict[str, list[dict[str, Any]]]
    optimizer_result: dict[str, Any]
    optimizer_backend: str | None
    conflicts: list[str]

    # Verification state
    pre_verification: dict[str, Any]
    final_verification: dict[str, Any]

    # Action / recovery state
    action_failure: dict[str, Any] | None
    noop: bool
