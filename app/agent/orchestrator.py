from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from app.agent.checkpoint import (
    sqlite_checkpointer,
)

from app.agent.graph import (
    build_reconcile_graph,
)

from app.agent.nodes import (
    AgentRuntime,
)

from app.agent.state import (
    GraphState,
)

from app.config import (
    Settings,
)

from app.storage.repository import (
    AthleteRepository,
)


class AthleteOpsOrchestrator:
    """
    Compatibility wrapper around the LangGraph workflow.

    Existing callers remain unchanged:

        FastAPI route
        background worker
        pytest suite

    Only the internal orchestration mechanism changes.
    """

    def __init__(
        self,
        repo: AthleteRepository,
        settings: Settings,
    ):
        self.repo = repo
        self.settings = settings

    # ==========================================================
    # Convert internal graph state into the existing API shape
    # ==========================================================

    @staticmethod
    def _public_result(
        state: GraphState,
    ) -> dict[str, Any]:

        status = state.get(
            "status",
            "FAILED",
        )

        run_id = state["run_id"]

        # ------------------------------------------------------
        # VERIFIED
        # ------------------------------------------------------

        if status == "VERIFIED":

            result: dict[str, Any] = {
                "run_id":
                    run_id,

                "status":
                    "VERIFIED",

                "plan_id":
                    state.get(
                        "plan_id"
                    ),

                "plan_version":
                    state.get(
                        "plan_version"
                    ),

                "parent_plan_id":
                    state.get(
                        "parent_plan_id"
                    ),

                "verification":
                    state.get(
                        "final_verification",
                        {},
                    ),
            }

            if state.get(
                "noop"
            ):

                result["noop"] = True

            else:

                result["diff"] = state.get(
                    "diff",
                    {},
                )

                result["optimizer_backend"] = (
                    state.get(
                        "optimizer_backend"
                    )
                )

            return result

        # ------------------------------------------------------
        # INFEASIBLE
        # ------------------------------------------------------

        if status == "INFEASIBLE":

            return {
                "run_id":
                    run_id,

                "status":
                    "INFEASIBLE",

                "conflicts":
                    state.get(
                        "conflicts",
                        [],
                    ),

                "optimizer_backend":
                    state.get(
                        "optimizer_backend"
                    ),
            }

        # ------------------------------------------------------
        # STALE STATE
        # ------------------------------------------------------

        if status == "STALE_STATE":

            return {
                "run_id":
                    run_id,

                "status":
                    "STALE_STATE",

                "error":
                    state.get(
                        "error"
                    ),

                "world_state_hash":
                    state.get(
                        "world_state_hash"
                    ),
            }

        # ------------------------------------------------------
        # VERIFICATION FAILED
        # ------------------------------------------------------

        if (
            status
            == "VERIFICATION_FAILED"
        ):

            verification = (
                state.get(
                    "final_verification"
                )
                or
                state.get(
                    "pre_verification"
                )
                or
                {}
            )

            return {
                "run_id":
                    run_id,

                "status":
                    "VERIFICATION_FAILED",

                "plan_id":
                    state.get(
                        "plan_id"
                    ),

                "plan_version":
                    state.get(
                        "plan_version"
                    ),

                "verification":
                    verification,

                "error":
                    state.get(
                        "error"
                    ),
            }

        # ------------------------------------------------------
        # Anything else is an orchestration failure
        # ------------------------------------------------------

        return {
            "run_id":
                run_id,

            "status":
                "FAILED",

            "error":
                (
                    state.get(
                        "error"
                    )
                    or
                    f"UNEXPECTED_TERMINAL_STATUS:{status}"
                ),
        }

    # ==========================================================
    # Public reconcile API
    # ==========================================================

    def reconcile(
        self,
        athlete_id: str,
        reason: str = "USER_REQUEST",
    ) -> dict[str, Any]:

        run_id = str(
            uuid4()
        )

        runtime = AgentRuntime(
            self.repo,
            self.settings,
        )

        initial_state: GraphState = {
    # Execution identity
    "run_id": run_id,
    "athlete_id": athlete_id,
    "reason": reason,
    "current_reason": reason,
    "attempt": 1,
    "status": "INITIALIZED",
    "error": None,

    # Authoritative world state
    # These were missing and are causing your Pylance error.
    "world": {},
    "world_state_hash": "",

    # Plan lineage
    "parent_plan_id": None,
    "plan_id": None,
    "plan_version": None,
    "diff": {},

    # Planning
    "intent": {},
    "candidates": {},
    "optimizer_result": {},
    "optimizer_backend": None,
    "conflicts": [],

    # Verification
    "pre_verification": {},
    "final_verification": {},

    # Actions/recovery
    "action_failure": None,
    "noop": False,
}
        config = {
            "configurable": {
                # Each reconciliation run gets its own
                # checkpoint history.
                #
                # athlete_id remains domain identity.
                # run_id becomes LangGraph thread identity.
                "thread_id":
                    run_id,
            },

            # Framework-level circuit breaker.
            #
            # The actual business-level retry boundary
            # is still settings.max_replan_attempts.
            "recursion_limit":
                100,
        }

        with sqlite_checkpointer() as checkpointer:

            graph = build_reconcile_graph(
                runtime,
                checkpointer,
            )

            final_state = cast(
                GraphState,
                graph.invoke(
                    initial_state,
                    config=config,
            ),
            )

        return self._public_result(
            final_state
        )