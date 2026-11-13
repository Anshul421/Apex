from __future__ import annotations

from typing import Any

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from app.agent.nodes import (
    AgentRuntime,
)

from app.agent.state import (
    GraphState,
)


# ==============================================================
# Routers
# ==============================================================


def _after_observe(
    state: GraphState,
) -> str:

    # Observation may finish a no-op run or reject stale input before planning begins.
    if state.get("status") in {
        "STALE_STATE",
        "VERIFIED",
        "VERIFICATION_FAILED",
        "FAILED",
    }:
        return "end"

    return "intent"




def _after_intent(
    state: GraphState,
) -> str:

    if (
        state.get("status")
        == "INTENT_READY"
    ):
        return "candidates"

    return "end"


def _after_optimize(
    state: GraphState,
) -> str:

    if (
        state.get("status")
        == "INFEASIBLE"
    ):
        return "end"

    if (
        state.get("status")
        == "OPTIMIZED"
    ):
        return "persist"

    return "end"


def _after_pre_verify(
    state: GraphState,
) -> str:

    if (
        state.get("status")
        == "PRE_VERIFIED"
    ):
        return "actions"

    return "end"


def _after_actions(
    state: GraphState,
) -> str:

    if (
        state.get("status")
        == "ACTION_REPLAN_REQUIRED"
    ):
        return "replan"

    # Even skipped actions require a fresh observation before final verification.
    if state.get("status") in {
        "ACTIONS_CONFIRMED",
        "ACTIONS_SKIPPED",
    }:
        return "reobserve"

    return "end"


def _after_reobserve(
    state: GraphState,
) -> str:

    if (
        state.get("status")
        == "WORLD_REOBSERVED"
    ):
        return "final_verify"

    return "end"


def _after_final_verify(
    state: GraphState,
) -> str:

    if (
        state.get("status")
        == "REPLAN_REQUIRED"
    ):
        return "replan"

    return "end"


def _after_replan_guard(
    state: GraphState,
) -> str:

    if (
        state.get("status")
        == "REPLAN_READY"
    ):
        return "observe"

    return "end"


# ==============================================================
# Graph
# ==============================================================


def build_reconcile_graph(
    runtime: AgentRuntime,
    checkpointer: Any,
):
    """
    Build the AthleteOps reconcile state machine.

    LangGraph controls:

        sequencing
        branching
        recovery
        checkpoint state

    Existing deterministic services control:

        workload calculations
        candidate generation
        constraint solving
        verification
        action semantics
    """

    graph = StateGraph(
        GraphState
    )

    # ----------------------------------------------------------
    # Nodes
    # ----------------------------------------------------------

    graph.add_node(
        "start_run",
        runtime.start_run,
    )

    graph.add_node(
        "observe",
        runtime.observe_world,
    )

    graph.add_node(
        "intent",
        runtime.interpret_intent,
    )

    graph.add_node(
        "candidates",
        runtime.generate_candidates,
    )

    graph.add_node(
        "optimize",
        runtime.optimize_plan,
    )

    graph.add_node(
        "persist",
        runtime.persist_plan,
    )

    graph.add_node(
        "pre_verify",
        runtime.pre_action_verify,
    )

    graph.add_node(
        "actions",
        runtime.execute_actions,
    )

    graph.add_node(
        "reobserve",
        runtime.reobserve_after_actions,
    )

    graph.add_node(
        "final_verify",
        runtime.final_verify,
    )

    graph.add_node(
        "replan_guard",
        runtime.replan_guard,
    )

    # ----------------------------------------------------------
    # Entry
    # ----------------------------------------------------------

    graph.add_edge(
        START,
        "start_run",
    )

    graph.add_edge(
        "start_run",
        "observe",
    )

    # ----------------------------------------------------------
    # Observation routing
    # ----------------------------------------------------------

    graph.add_conditional_edges(
        "observe",
        _after_observe,
        {
            "intent":
                "intent",

            "end":
                END,
        },
    )

    # ----------------------------------------------------------
    # Semantic interpretation
    # ----------------------------------------------------------

    graph.add_conditional_edges(
        "intent",
        _after_intent,
        {
            "candidates":
                "candidates",

            "end":
                END,
        },
    )

    graph.add_edge(
        "candidates",
        "optimize",
    )

    # ----------------------------------------------------------
    # Important:
    # INFEASIBLE does not go to verifier.
    # ----------------------------------------------------------

    graph.add_conditional_edges(
        "optimize",
        _after_optimize,
        {
            "persist":
                "persist",

            "end":
                END,
        },
    )

    # ----------------------------------------------------------
    # Candidate verification
    # ----------------------------------------------------------

    graph.add_edge(
        "persist",
        "pre_verify",
    )

    graph.add_conditional_edges(
        "pre_verify",
        _after_pre_verify,
        {
            "actions":
                "actions",

            "end":
                END,
        },
    )

    # ----------------------------------------------------------
    # Tool execution
    # ----------------------------------------------------------

    graph.add_conditional_edges(
        "actions",
        _after_actions,
        {
            "replan":
                "replan_guard",

            "reobserve":
                "reobserve",

            "end":
                END,
        },
    )

    # ----------------------------------------------------------
    # Re-observe authoritative state after actions
    # ----------------------------------------------------------

    graph.add_conditional_edges(
        "reobserve",
        _after_reobserve,
        {
            "final_verify":
                "final_verify",

            "end":
                END,
        },
    )

    # ----------------------------------------------------------
    # Final independent verification
    # ----------------------------------------------------------

    graph.add_conditional_edges(
        "final_verify",
        _after_final_verify,
        {
            "replan":
                "replan_guard",

            "end":
                END,
        },
    )

    # ----------------------------------------------------------
    # Bounded recovery loop
    # ----------------------------------------------------------

    graph.add_conditional_edges(
        "replan_guard",
        _after_replan_guard,
        {
            "observe":
                "observe",

            "end":
                END,
        },
    )

    # ----------------------------------------------------------
    # Compile with persistence
    # ----------------------------------------------------------

    return graph.compile(
        checkpointer=checkpointer
    )