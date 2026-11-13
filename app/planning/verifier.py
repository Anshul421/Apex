from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.domain import LoadConstraintResult, SessionPlan, VerificationReport
from app.planning.load_adapter import SyntheticLoadAdapter
from app.planning.world import WorldSnapshot
from app.storage.models import Booking, CalendarEntry, PlanVersion, Session as SessionModel, ToolAction


class PlanVerifier:
    """Independent deterministic verifier.

    It does not consume planner assertions. It reconstructs checks from the stored plan,
    immutable-ish source observations in the WorldSnapshot, and current action receipts.
    """

    def __init__(self, db: DbSession, load_adapter: SyntheticLoadAdapter):
        self.db = db
        self.load_adapter = load_adapter

    @staticmethod
    def _session_plans(plan: PlanVersion) -> list[SessionPlan]:
        from datetime import timezone
        def aware(dt):
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        return [
            SessionPlan(
                logical_key=s.logical_key,
                session_type=s.session_type,
                start_time=aware(s.start_time),
                duration_minutes=s.duration_minutes,
                intended_load=s.intended_load,
                intensity=s.intensity,
                facility=s.facility,
            )
            for s in plan.sessions
        ]

    @staticmethod
    def _within_availability(session: SessionPlan, world: WorldSnapshot) -> bool:
        end = session.end_time
        for item in world.availability.get('windows', []):
            w_start = datetime.fromisoformat(item['start'])
            w_end = datetime.fromisoformat(item['end'])
            if session.start_time >= w_start and end <= w_end:
                return True
        return False

    def verify(self, plan: PlanVersion, world: WorldSnapshot, include_action_state: bool = True) -> VerificationReport:
        sessions = self._session_plans(plan)
        checks: list[LoadConstraintResult] = []
        violations: list[str] = []

        stale_plan_ok = plan.world_state_hash == world.world_state_hash
        checks.append(
            LoadConstraintResult(
                constraint_type='stale_state_check',
                passed=stale_plan_ok,
                details={'plan_hash': plan.world_state_hash, 'current_hash': world.world_state_hash},
            )
        )
        if not stale_plan_ok:
            violations.append('STALE_PLAN')

        freshness_ok = all(world.freshness.values())
        checks.append(
            LoadConstraintResult(
                constraint_type='source_freshness',
                passed=freshness_ok,
                details=world.freshness,
            )
        )
        if not freshness_ok:
            violations.extend([f'STALE_SOURCE:{k}' for k, v in world.freshness.items() if not v])

        # Recompute load constraints from raw source history and the stored plan.
        match_start = datetime.fromisoformat(world.match['start_time'])
        if match_start.tzinfo is None:
            match_start = match_start.replace(tzinfo=timezone.utc)
        load_eval = self.load_adapter.evaluate(
            world.gps.get('history', []),
            sessions,
            match_start,
        )
        checks.extend(load_eval.constraints)
        violations.extend(load_eval.violations)

        # No session overlaps.
        overlaps: list[str] = []
        ordered = sorted(sessions, key=lambda s: s.start_time)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if a.start_time < b.end_time and b.start_time < a.end_time:
                    overlaps.append(f'{a.logical_key}<->{b.logical_key}')
        checks.append(
            LoadConstraintResult(
                constraint_type='session_overlap',
                passed=not overlaps,
                details={'overlaps': overlaps},
            )
        )
        if overlaps:
            violations.extend([f'SESSION_OVERLAP:{x}' for x in overlaps])

        unavailable = [s.logical_key for s in sessions if not self._within_availability(s, world)]
        checks.append(
            LoadConstraintResult(
                constraint_type='athlete_availability',
                passed=not unavailable,
                details={'outside_windows': unavailable},
            )
        )
        if unavailable:
            violations.extend([f'ATHLETE_UNAVAILABLE:{x}' for x in unavailable])

        if include_action_state:
            session_rows = {s.logical_key: s for s in plan.sessions}
            calendar_entries = list(self.db.scalars(select(CalendarEntry).where(CalendarEntry.plan_id == plan.id)).all())
            calendar_session_ids = {e.session_id for e in calendar_entries if e.status == 'confirmed'}
            missing_calendar = [s.logical_key for s in plan.sessions if s.id not in calendar_session_ids]
            checks.append(
                LoadConstraintResult(
                    constraint_type='calendar_synchronized',
                    passed=not missing_calendar,
                    details={'missing_sessions': missing_calendar},
                )
            )
            if missing_calendar:
                violations.extend([f'CALENDAR_MISSING:{x}' for x in missing_calendar])

            bookings = list(self.db.scalars(select(Booking).where(Booking.plan_id == plan.id)).all())
            confirmed_booking_sessions = {b.session_id for b in bookings if b.status == 'confirmed'}
            facility_sessions = [s for s in plan.sessions if s.facility]
            missing_bookings = [s.logical_key for s in facility_sessions if s.id not in confirmed_booking_sessions]
            checks.append(
                LoadConstraintResult(
                    constraint_type='booking_confirmed',
                    passed=not missing_bookings,
                    details={'missing_sessions': missing_bookings},
                )
            )
            if missing_bookings:
                violations.extend([f'BOOKING_MISSING:{x}' for x in missing_bookings])

            outstanding = list(
                self.db.scalars(
                    select(ToolAction).where(ToolAction.plan_id == plan.id, ToolAction.status == 'pending')
                ).all()
            )
            checks.append(
                LoadConstraintResult(
                    constraint_type='outstanding_actions',
                    limit=0,
                    measured_value=len(outstanding),
                    passed=not outstanding,
                    details={'action_ids': [a.id for a in outstanding]},
                )
            )
            if outstanding:
                violations.append(f'OUTSTANDING_ACTIONS:{len(outstanding)}')

        state_snapshot = {
            'workload_version': world.gps_version,
            'wellness_version': world.wellness_version,
            'match_version': world.fixture_version,
            'availability_version': world.availability_version,
            'load_algorithm': world.load_algorithm_version,
            'world_state_hash': world.world_state_hash,
            'plan_version': plan.version,
            'parent_plan_id': plan.parent_plan_id,
        }
        return VerificationReport(
            passed=not violations,
            plan_id=plan.id,
            state_snapshot=state_snapshot,
            checks=checks,
            violations=violations,
        )
