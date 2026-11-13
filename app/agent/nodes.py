from __future__ import annotations

from datetime import timezone
from typing import Any

from app.agent.intent_provider import (
    IntentProviderError,
    build_intent_provider,
)
from app.agent.policies import (
    PolicyViolation,
    require_fresh_world,
)
from app.agent.state import GraphState

from app.config import Settings

from app.domain import (
    OptimizerResult,
    SessionCandidate,
    SessionPlan,
    TrainingIntent,
)

from app.planning.candidate_generator import (
    CandidateGenerator,
)

from app.planning.load_adapter import (
    EvaluatorConfig,
    SyntheticLoadAdapter,
)

from app.planning.optimizer import (
    ConstraintOptimizer,
)

from app.planning.verifier import (
    PlanVerifier,
)

from app.planning.world import (
    WorldSnapshot,
    build_world_snapshot,
)

from app.storage.models import (
    PlanVersion,
)

from app.storage.repository import (
    AthleteRepository,
)

from app.tools.booking import (
    BookingConflict,
    SandboxBookingTool,
)

from app.tools.browser import (
    SandboxWebReader,
)

from app.tools.calendar import (
    SandboxCalendarTool,
)


class AgentRuntime:
    """
    Runtime dependencies and LangGraph node implementations.

    Important:

    Repository/session/tool objects are NOT stored inside GraphState.

    LangGraph checkpoints workflow state.

    The application database remains the authoritative
    source of product state.
    """

    def __init__(
        self,
        repo: AthleteRepository,
        settings: Settings,
    ):
        self.repo = repo
        self.settings = settings

        evaluator_config = EvaluatorConfig.from_settings(
            settings
        )

        self.load_adapter = SyntheticLoadAdapter(
            evaluator_config
        )

        # Semantic intent may come from a structured LLM, but the provider
        # has no tools and cannot change deterministic solver/verifier logic.
        self.intent_provider = build_intent_provider(settings)

        self.generator = CandidateGenerator()

        self.optimizer = ConstraintOptimizer(
            self.load_adapter
        )

        self.calendar = SandboxCalendarTool(
            repo
        )

        self.booking = SandboxBookingTool(
            repo
        )

        self.browser = SandboxWebReader(
            repo
        )

    # ============================================================
    # Helpers
    # ============================================================

    @staticmethod
    def _aware(dt):
        if dt.tzinfo is not None:
            return dt

        return dt.replace(
            tzinfo=timezone.utc
        )

    @classmethod
    def _to_plan_sessions(
        cls,
        plan: PlanVersion | None,
    ) -> list[SessionPlan]:

        if not plan:
            return []

        return [
            SessionPlan(
                logical_key=session.logical_key,
                session_type=session.session_type,
                start_time=cls._aware(
                    session.start_time
                ),
                duration_minutes=session.duration_minutes,
                intended_load=session.intended_load,
                intensity=session.intensity,
                facility=session.facility,
            )
            for session in plan.sessions
        ]

    @staticmethod
    def _session_signature(
        session: SessionPlan,
    ) -> tuple:

        return (
            session.session_type,
            session.start_time.isoformat(),
            session.duration_minutes,
            session.intended_load,
            str(session.intensity),
            session.facility,
        )

    def _diff(
        self,
        parent: PlanVersion | None,
        sessions: list[SessionPlan],
    ) -> dict[str, Any]:

        if not parent:
            return {
                "added": [
                    session.logical_key
                    for session in sessions
                ],
                "changed": [],
                "unchanged": [],
                "removed": [],
            }

        old = {
            session.logical_key: session
            for session in self._to_plan_sessions(
                parent
            )
        }

        new = {
            session.logical_key: session
            for session in sessions
        }

        added = sorted(
            set(new) - set(old)
        )

        removed = sorted(
            set(old) - set(new)
        )

        changed: list[str] = []
        unchanged: list[str] = []

        details: dict[str, Any] = {}

        for key in sorted(
            set(old) & set(new)
        ):

            if (
                self._session_signature(old[key])
                ==
                self._session_signature(new[key])
            ):
                unchanged.append(
                    key
                )

            else:
                changed.append(
                    key
                )

                details[key] = {
                    "from": old[key].model_dump(
                        mode="json"
                    ),
                    "to": new[key].model_dump(
                        mode="json"
                    ),
                }

        return {
            "added": added,
            "changed": changed,
            "unchanged": unchanged,
            "removed": removed,
            "details": details,
        }

    def _record(
        self,
        run_id: str,
        athlete_id: str,
        event_type: str,
        payload: dict[str, Any],
        plan_id: str | None = None,
    ) -> None:

        self.repo.add_agent_event(
            run_id,
            athlete_id,
            event_type,
            payload,
            plan_id,
        )

    def _verify_and_persist(
        self,
        plan: PlanVersion,
        world: WorldSnapshot,
        include_actions: bool,
    ):

        verifier = PlanVerifier(
            self.repo.db,
            self.load_adapter,
        )

        report = verifier.verify(
            plan,
            world,
            include_action_state=include_actions,
        )

        self.repo.replace_constraint_results(
            plan.id,
            [
                check.model_dump(
                    mode="json"
                )
                for check in report.checks
            ],
        )

        self.repo.add_verification(
            plan.id,
            report.state_snapshot,
            report.passed,
            report.violations,
        )

        return report

    def _execute_plan(
        self,
        run_id: str,
        plan: PlanVersion,
    ) -> tuple[
        bool,
        dict[str, Any] | None,
    ]:
        """
        Execute bookings first.

        Calendar writes happen only after all required
        bookings succeed.

        A failed booking becomes observed environment
        state and causes replanning.
        """

        for session in plan.sessions:

            if not session.facility:
                continue

            fact = self.browser.facility_slot_fact(
                athlete_id=plan.athlete_id,
                facility=session.facility,
                start_time=session.start_time,
                plan_id=plan.id,
            )

            self._record(
                run_id,
                plan.athlete_id,
                "WEB_FACT_OBSERVED",
                fact.model_dump(
                    mode="json"
                ),
                plan.id,
            )

            try:

                receipt = self.booking.reserve(
                    plan.athlete_id,
                    plan,
                    session,
                )

                self._record(
                    run_id,
                    plan.athlete_id,
                    "BOOKING_RECEIPT",
                    receipt,
                    plan.id,
                )

            except BookingConflict as exc:

                failure = {
                    "reason": "BOOKING_CONFLICT",
                    "facility": exc.facility,
                    "start_time": exc.start_time,
                    "code": "SLOT_UNAVAILABLE",
                }

                self._record(
                    run_id,
                    plan.athlete_id,
                    "BOOKING_FAILED",
                    failure,
                    plan.id,
                )

                return (
                    False,
                    failure,
                )

        # Only mutate the calendar once bookings succeeded.
        for session in plan.sessions:

            receipt = self.calendar.upsert_session(
                plan.athlete_id,
                plan,
                session,
            )

            self._record(
                run_id,
                plan.athlete_id,
                "CALENDAR_RECEIPT",
                receipt,
                plan.id,
            )

        return (
            True,
            None,
        )

    @staticmethod
    def _world_from_state(
        state: GraphState,
    ) -> WorldSnapshot:

        return WorldSnapshot.model_validate(
            state["world"]
        )

    def _parent_from_state(
        self,
        state: GraphState,
    ) -> PlanVersion | None:

        parent_id = state.get(
            "parent_plan_id"
        )

        if parent_id:
            return self.repo.get_plan(
                parent_id
            )

        return None

    # ============================================================
    # Node: Start run
    # ============================================================

    def start_run(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        run_id = state["run_id"]
        athlete_id = state["athlete_id"]

        reason = state.get(
            "reason",
            "USER_REQUEST",
        )

        parent = self.repo.latest_plan(
            athlete_id
        )

        self._record(
            run_id,
            athlete_id,
            "RUN_STARTED",
            {
                "reason": reason,
            },
        )

        self.repo.db.commit()

        return {
            "current_reason": reason,
            "attempt": 1,
            "parent_plan_id": (
                parent.id
                if parent
                else None
            ),
            "status": "RUNNING",
            "error": None,
            "noop": False,
            "conflicts": [],
        }

    # ============================================================
    # Node: Observe
    # ============================================================

    def observe_world(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        run_id = state["run_id"]
        athlete_id = state["athlete_id"]

        attempt = state.get(
            "attempt",
            1,
        )

        world = build_world_snapshot(
            self.repo,
            athlete_id,
            self.settings,
        )

        parent = self._parent_from_state(
            state
        )

        self._record(
            run_id,
            athlete_id,
            "WORLD_OBSERVED",
            {
                "attempt": attempt,

                "world_state_hash":
                    world.world_state_hash,

                "versions": {
                    "gps":
                        world.gps_version,

                    "wellness":
                        world.wellness_version,

                    "fixture":
                        world.fixture_version,

                    "availability":
                        world.availability_version,

                    "load_algorithm":
                        world.load_algorithm_version,
                },

                "freshness":
                    world.freshness,
            },

            parent.id
            if parent
            else None,
        )

        try:

            require_fresh_world(
                world
            )

        except PolicyViolation as exc:

            self._record(
                run_id,
                athlete_id,
                "RUN_BLOCKED_STALE_STATE",
                {
                    "error": str(exc),
                },
            )

            self.repo.db.commit()

            return {
                "world":
                    world.model_dump(
                        mode="json"
                    ),

                "world_state_hash":
                    world.world_state_hash,

                "status":
                    "STALE_STATE",

                "error":
                    str(exc),
            }

        current_reason = state.get(
            "current_reason",
            state.get(
                "reason",
                "USER_REQUEST",
            ),
        )

        # --------------------------------------------------------
        # Idempotent reconcile
        # --------------------------------------------------------

        if (
            parent
            and
            parent.world_state_hash
            ==
            world.world_state_hash
            and
            parent.status
            in {
                "verified",
                "executed",
            }
            and
            current_reason
            in {
                "USER_REQUEST",
                "SCHEDULED_RECONCILE",
            }
        ):

            report = self._verify_and_persist(
                parent,
                world,
                include_actions=True,
            )

            self._record(
                run_id,
                athlete_id,
                "RUN_NOOP",
                {
                    "plan_id":
                        parent.id,

                    "verified":
                        report.passed,
                },
                parent.id,
            )

            self.repo.db.commit()

            return {
                "world":
                    world.model_dump(
                        mode="json"
                    ),

                "world_state_hash":
                    world.world_state_hash,

                "status":
                    (
                        "VERIFIED"
                        if report.passed
                        else "VERIFICATION_FAILED"
                    ),

                "plan_id":
                    parent.id,

                "plan_version":
                    parent.version,

                "parent_plan_id":
                    parent.parent_plan_id,

                "final_verification":
                    report.model_dump(
                        mode="json"
                    ),

                "noop":
                    True,

                "error":
                    (
                        None
                        if report.passed
                        else "NOOP_REVERIFICATION_FAILED"
                    ),
            }

        self.repo.db.commit()

        return {
            "world":
                world.model_dump(
                    mode="json"
                ),

            "world_state_hash":
                world.world_state_hash,

            "status":
                "OBSERVED",

            "error":
                None,
        }

    # ============================================================
    # Node: Intent
    # ============================================================

    def interpret_intent(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        world = self._world_from_state(
            state
        )

        reason = state.get(
            "current_reason",
            state["reason"],
        )

        parent = self._parent_from_state(
            state
        )

        try:
            decision = self.intent_provider.create_intent(
                world,
                reason,
            )
        except IntentProviderError as exc:
            self._record(
                state["run_id"],
                state["athlete_id"],
                "INTENT_FAILED",
                {
                    "error_code": exc.code,
                    "trigger_reason": reason,
                },
                (
                    parent.id
                    if parent
                    else None
                ),
            )

            self.repo.db.commit()

            return {
                "status": "FAILED",
                "error": f"INTENT_PROVIDER_FAILED:{exc.code}",
            }

        intent = decision.intent
        intent_payload = intent.model_dump(
            mode="json"
        )

        self._record(
            state["run_id"],
            state["athlete_id"],
            "INTENT_CREATED",
            {
                **intent_payload,
                "_meta": {
                    "provider": decision.provider,
                    "model": decision.model,
                    "fallback_used": decision.fallback_used,
                    "primary_error_code": decision.primary_error_code,
                },
            },
            (
                parent.id
                if parent
                else None
            ),
        )

        self.repo.db.commit()

        return {
            "intent": intent_payload,
            "status": "INTENT_READY",
            "error": None,
        }

    # ============================================================
    # Node: Generate candidates
    # ============================================================

    def generate_candidates(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        world = self._world_from_state(
            state
        )

        intent = TrainingIntent.model_validate(
            state["intent"]
        )

        parent = self._parent_from_state(
            state
        )

        parent_sessions = self._to_plan_sessions(
            parent
        )

        candidates = self.generator.generate_candidates(
            world,
            intent,
            parent_sessions,
        )

        candidate_counts = {
            key: len(items)
            for key, items
            in candidates.items()
        }

        self._record(
            state["run_id"],
            state["athlete_id"],
            "CANDIDATES_GENERATED",
            {
                "counts":
                    candidate_counts,
            },
            (
                parent.id
                if parent
                else None
            ),
        )

        self.repo.db.commit()

        return {
            "candidates": {
                key: [
                    candidate.model_dump(
                        mode="json"
                    )
                    for candidate
                    in items
                ]
                for key, items
                in candidates.items()
            },

            "status":
                "CANDIDATES_READY",
        }

    # ============================================================
    # Node: OR-Tools optimization
    # ============================================================

    def optimize_plan(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        world = self._world_from_state(
            state
        )

        parent = self._parent_from_state(
            state
        )

        parent_sessions = self._to_plan_sessions(
            parent
        )

        candidates = {
            key: [
                SessionCandidate.model_validate(
                    item
                )
                for item in items
            ]
            for key, items
            in state["candidates"].items()
        }

        solution = self.optimizer.solve(
            candidates,
            world,
            parent_sessions,
        )

        self._record(
            state["run_id"],
            state["athlete_id"],
            "OPTIMIZER_RESULT",
            solution.model_dump(
                mode="json"
            ),
            (
                parent.id
                if parent
                else None
            ),
        )

        self.repo.db.commit()

        # IMPORTANT:
        # INFEASIBLE stops here.
        # It is NOT sent into the verifier.

        if (
            solution.status
            not in {
                "FEASIBLE",
                "OPTIMAL",
            }
        ):

            return {
                "optimizer_result":
                    solution.model_dump(
                        mode="json"
                    ),

                "optimizer_backend":
                    solution.backend,

                "conflicts":
                    solution.conflicts,

                "status":
                    "INFEASIBLE",
            }

        return {
            "optimizer_result":
                solution.model_dump(
                    mode="json"
                ),

            "optimizer_backend":
                solution.backend,

            "conflicts":
                [],

            "status":
                "OPTIMIZED",
        }

    # ============================================================
    # Node: Persist proposed plan
    # ============================================================

    def persist_plan(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        solution = OptimizerResult.model_validate(
            state["optimizer_result"]
        )

        parent = self._parent_from_state(
            state
        )

        intent = TrainingIntent.model_validate(
            state["intent"]
        )

        world = self._world_from_state(
            state
        )

        diff = self._diff(
            parent,
            solution.sessions,
        )

        current_reason = state.get(
            "current_reason",
            state.get(
                "reason",
                "USER_REQUEST",
            ),
        )

        plan_reason = (
            current_reason
            if current_reason
            != "USER_REQUEST"
            else intent.reason
        )

        plan = self.repo.create_plan(
            athlete_id=
                state["athlete_id"],

            parent_plan_id=
                (
                    parent.id
                    if parent
                    else None
                ),

            reason=
                plan_reason,

            world_state_hash=
                world.world_state_hash,

            status=
                "proposed",

            intent=
                intent.model_dump(
                    mode="json"
                ),

            sessions=
                solution.sessions,

            diff=
                diff,
        )

        self._record(
            state["run_id"],
            state["athlete_id"],
            "PLAN_PERSISTED",
            {
                "plan_id":
                    plan.id,

                "version":
                    plan.version,

                "diff":
                    diff,
            },
            plan.id,
        )

        self.repo.db.commit()

        return {
            "plan_id":
                plan.id,

            "plan_version":
                plan.version,

            "parent_plan_id":
                plan.parent_plan_id,

            "diff":
                diff,

            "status":
                "PLAN_PERSISTED",
        }

    # ============================================================
    # Node: Independent pre-action verifier
    # ============================================================

    def pre_action_verify(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        plan_id = state.get(
            "plan_id"
        )

        if not plan_id:

            return {
                "status":
                    "FAILED",

                "error":
                    "MISSING_PLAN_ID_BEFORE_PRE_ACTION_VERIFY",
            }

        plan = self.repo.get_plan(
            plan_id
        )

        if not plan:

            return {
                "status":
                    "FAILED",

                "error":
                    f"PLAN_NOT_FOUND:{plan_id}",
            }

        world = self._world_from_state(
            state
        )

        # Calendar + booking have NOT happened yet.
        report = self._verify_and_persist(
            plan,
            world,
            include_actions=False,
        )

        if not report.passed:

            self.repo.update_plan_status(
                plan,
                "failed",
            )

            self._record(
                state["run_id"],
                state["athlete_id"],
                "PRE_ACTION_VERIFICATION_FAILED",
                {
                    "violations":
                        report.violations,
                },
                plan.id,
            )

            self.repo.db.commit()

            # Do NOT blindly re-run the solver.
            # Solver/verifier disagreement is an invariant failure.
            return {
                "pre_verification":
                    report.model_dump(
                        mode="json"
                    ),

                "status":
                    "VERIFICATION_FAILED",

                "error":
                    "PRE_ACTION_INVARIANT_FAILURE",
            }

        next_status = (
            "verified_pending_execution"
            if self.settings.auto_execute_actions
            else "verified"
        )

        self.repo.update_plan_status(
            plan,
            next_status,
        )

        self._record(
            state["run_id"],
            state["athlete_id"],
            "PRE_ACTION_VERIFIED",
            {
                "passed":
                    True,
            },
            plan.id,
        )

        self.repo.db.commit()

        return {
            "pre_verification":
                report.model_dump(
                    mode="json"
                ),

            "status":
                "PRE_VERIFIED",

            "error":
                None,
        }

    # ============================================================
    # Node: Execute authorized tools
    # ============================================================

    def execute_actions(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        plan_id = state.get(
            "plan_id"
        )

        if not plan_id:

            return {
                "status":
                    "FAILED",

                "error":
                    "MISSING_PLAN_ID_BEFORE_ACTIONS",
            }

        plan = self.repo.get_plan(
            plan_id
        )

        if not plan:

            return {
                "status":
                    "FAILED",

                "error":
                    f"PLAN_NOT_FOUND:{plan_id}",
            }

        if not self.settings.auto_execute_actions:

            return {
                "status":
                    "ACTIONS_SKIPPED",

                "action_failure":
                    None,
            }

        self.repo.update_plan_status(
            plan,
            "executing",
        )

        ok, failure = self._execute_plan(
            state["run_id"],
            plan,
        )

        if not ok:

            self.repo.update_plan_status(
                plan,
                "invalidated",
            )

            self._record(
                state["run_id"],
                state["athlete_id"],
                "REPLAN_TRIGGERED",
                (
                    failure
                    or {
                        "reason":
                            "ACTION_FAILURE"
                    }
                ),
                plan.id,
            )

            # Commit the observed external failure BEFORE replanning.
            self.repo.db.commit()

            return {
                "parent_plan_id":
                    plan.id,

                "current_reason":
                    (
                        failure
                        or {}
                    ).get(
                        "reason",
                        "ACTION_FAILURE",
                    ),

                "action_failure":
                    failure,

                "status":
                    "ACTION_REPLAN_REQUIRED",
            }

        self.repo.db.commit()

        return {
            "action_failure":
                None,

            "status":
                "ACTIONS_CONFIRMED",
        }

    # ============================================================
    # Node: Reobserve after external actions
    # ============================================================

    def reobserve_after_actions(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        world = build_world_snapshot(
            self.repo,
            state["athlete_id"],
            self.settings,
        )

        self._record(
            state["run_id"],
            state["athlete_id"],
            "WORLD_REOBSERVED_AFTER_ACTIONS",
            {
                "world_state_hash":
                    world.world_state_hash,

                "versions": {
                    "gps":
                        world.gps_version,

                    "wellness":
                        world.wellness_version,

                    "fixture":
                        world.fixture_version,

                    "availability":
                        world.availability_version,

                    "load_algorithm":
                        world.load_algorithm_version,
                },

                "freshness":
                    world.freshness,
            },

            state.get(
                "plan_id"
            ),
        )

        try:

            require_fresh_world(
                world
            )

        except PolicyViolation as exc:

            self._record(
                state["run_id"],
                state["athlete_id"],
                "RUN_BLOCKED_STALE_STATE",
                {
                    "error":
                        str(exc),
                },
                state.get(
                    "plan_id"
                ),
            )

            self.repo.db.commit()

            return {
                "world":
                    world.model_dump(
                        mode="json"
                    ),

                "world_state_hash":
                    world.world_state_hash,

                "status":
                    "STALE_STATE",

                "error":
                    str(exc),
            }

        self.repo.db.commit()

        return {
            "world":
                world.model_dump(
                    mode="json"
                ),

            "world_state_hash":
                world.world_state_hash,

            "status":
                "WORLD_REOBSERVED",

            "error":
                None,
        }

    # ============================================================
    # Node: Independent final verifier
    # ============================================================

    def final_verify(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        plan_id = state.get(
            "plan_id"
        )

        if not plan_id:

            return {
                "status":
                    "FAILED",

                "error":
                    "MISSING_PLAN_ID_BEFORE_FINAL_VERIFY",
            }

        plan = self.repo.get_plan(
            plan_id
        )

        if not plan:

            return {
                "status":
                    "FAILED",

                "error":
                    f"PLAN_NOT_FOUND:{plan_id}",
            }

        world = self._world_from_state(
            state
        )

        report = self._verify_and_persist(
            plan,
            world,
            include_actions=
                self.settings.auto_execute_actions,
        )

        # --------------------------------------------------------
        # Success
        # --------------------------------------------------------

        if report.passed:

            self.repo.update_plan_status(
                plan,
                (
                    "executed"
                    if self.settings.auto_execute_actions
                    else "verified"
                ),
            )

            self._record(
                state["run_id"],
                state["athlete_id"],
                "FINAL_VERIFICATION",
                {
                    "passed":
                        True,

                    "violations":
                        [],

                    "state":
                        report.state_snapshot,
                },
                plan.id,
            )

            self.repo.db.commit()

            return {
                "final_verification":
                    report.model_dump(
                        mode="json"
                    ),

                "status":
                    "VERIFIED",

                "error":
                    None,
            }

        # --------------------------------------------------------
        # Legitimate world-state change
        # --------------------------------------------------------

        if "STALE_PLAN" in report.violations:

            self.repo.update_plan_status(
                plan,
                "invalidated",
            )

            self._record(
                state["run_id"],
                state["athlete_id"],
                "REPLAN_TRIGGERED",
                {
                    "reason":
                        "WORLD_CHANGED_DURING_EXECUTION",

                    "violations":
                        report.violations,
                },
                plan.id,
            )

            self.repo.db.commit()

            return {
                "final_verification":
                    report.model_dump(
                        mode="json"
                    ),

                "parent_plan_id":
                    plan.id,

                "current_reason":
                    "WORLD_CHANGED_DURING_EXECUTION",

                "status":
                    "REPLAN_REQUIRED",

                "error":
                    None,
            }

        # --------------------------------------------------------
        # Internal invariant failure
        # --------------------------------------------------------

        self.repo.update_plan_status(
            plan,
            "failed",
        )

        self._record(
            state["run_id"],
            state["athlete_id"],
            "FINAL_VERIFICATION_FAILED",
            {
                "violations":
                    report.violations,
            },
            plan.id,
        )

        self.repo.db.commit()

        # Deliberately DO NOT repeatedly replan here.
        #
        # If the optimizer and verifier disagree under the same
        # world snapshot, that indicates a code/invariant bug.
        return {
            "final_verification":
                report.model_dump(
                    mode="json"
                ),

            "status":
                "VERIFICATION_FAILED",

            "error":
                "FINAL_VERIFIER_INVARIANT_FAILURE",
        }

    # ============================================================
    # Node: Bounded replan guard
    # ============================================================

    def replan_guard(
        self,
        state: GraphState,
    ) -> dict[str, Any]:

        next_attempt = (
            state.get(
                "attempt",
                1,
            )
            + 1
        )

        if (
            next_attempt
            >
            self.settings.max_replan_attempts
        ):

            self._record(
                state["run_id"],
                state["athlete_id"],
                "RUN_FAILED_MAX_REPLANS",
                {
                    "attempt":
                        next_attempt,

                    "max_replan_attempts":
                        self.settings.max_replan_attempts,
                },

                state.get(
                    "plan_id"
                ),
            )

            self.repo.db.commit()

            return {
                "attempt":
                    next_attempt,

                "status":
                    "FAILED",

                "error":
                    "MAX_REPLAN_ATTEMPTS_EXCEEDED",
            }

        self._record(
            state["run_id"],
            state["athlete_id"],
            "REPLAN_ATTEMPT_STARTED",
            {
                "attempt":
                    next_attempt,

                "reason":
                    state.get(
                        "current_reason"
                    ),
            },

            state.get(
                "parent_plan_id"
            ),
        )

        self.repo.db.commit()

        # Clear attempt-local data.
        # Keep:
        #   run_id
        #   athlete_id
        #   reason
        #   current_reason
        #   parent_plan_id

        return {
            "attempt":
                next_attempt,

            "world":
                {},

            "world_state_hash":
                "",

            "intent":
                {},

            "candidates":
                {},

            "optimizer_result":
                {},

            "optimizer_backend":
                None,

            "conflicts":
                [],

            "plan_id":
                None,

            "plan_version":
                None,

            "diff":
                {},

            "pre_verification":
                {},

            "final_verification":
                {},

            "action_failure":
                None,

            "noop":
                False,

            "status":
                "REPLAN_READY",

            "error":
                None,
        }