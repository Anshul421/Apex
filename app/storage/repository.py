from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domain import SessionPlan
from app.storage.models import (
    AgentEvent,
    Athlete,
    Booking,
    CalendarEntry,
    ConstraintResult,
    FacilitySlot,
    Match,
    Observation,
    PlanVersion,
    Session as SessionModel,
    Tenant,
    ToolAction,
    User,
    VerificationRun,
    WebEvidence,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AthleteRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_identity(self, tenant_id: str, subject: str) -> User:
        tenant = self.db.get(Tenant, tenant_id)
        if not tenant:
            tenant = Tenant(id=tenant_id, name=tenant_id)
            self.db.add(tenant)
            self.db.flush()
        user = self.db.scalar(
            select(User).where(User.tenant_id == tenant_id, User.external_subject == subject)
        )
        if not user:
            user = User(tenant_id=tenant_id, external_subject=subject)
            self.db.add(user)
            self.db.flush()
        return user

    def create_athlete(self, tenant_id: str, name: str, objective: str, timezone_name: str = 'UTC') -> Athlete:
        athlete = Athlete(tenant_id=tenant_id, name=name, objective=objective, timezone_name=timezone_name)
        self.db.add(athlete)
        self.db.flush()
        return athlete

    def get_athlete(self, athlete_id: str, tenant_id: str | None = None) -> Athlete | None:
        stmt = select(Athlete).where(Athlete.id == athlete_id)
        if tenant_id is not None:
            stmt = stmt.where(Athlete.tenant_id == tenant_id)
        return self.db.scalar(stmt)

    def add_observation(
        self,
        athlete_id: str,
        source: str,
        observed_at: datetime,
        source_version: str,
        payload: dict,
        freshness: str = 'fresh',
    ) -> Observation:
        row = Observation(
            athlete_id=athlete_id,
            source=source,
            observed_at=observed_at,
            source_version=source_version,
            payload=payload,
            freshness=freshness,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def latest_observation(self, athlete_id: str, source: str) -> Observation | None:
        return self.db.scalar(
            select(Observation)
            .where(Observation.athlete_id == athlete_id, Observation.source == source)
            .order_by(desc(Observation.created_at), desc(Observation.observed_at))
            .limit(1)
        )

    def list_observations(self, athlete_id: str, source: str | None = None) -> list[Observation]:
        stmt = select(Observation).where(Observation.athlete_id == athlete_id)
        if source:
            stmt = stmt.where(Observation.source == source)
        return list(self.db.scalars(stmt.order_by(Observation.observed_at)).all())

    def add_match(
        self,
        athlete_id: str,
        start_time: datetime,
        venue: str,
        revision: int,
        source_version: str,
    ) -> Match:
        row = Match(
            athlete_id=athlete_id,
            start_time=start_time,
            venue=venue,
            revision=revision,
            source_version=source_version,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def latest_match(self, athlete_id: str) -> Match | None:
        return self.db.scalar(
            select(Match)
            .where(Match.athlete_id == athlete_id)
            .order_by(desc(Match.revision), desc(Match.created_at))
            .limit(1)
        )

    def latest_plan(self, athlete_id: str) -> PlanVersion | None:
        return self.db.scalar(
            select(PlanVersion)
            .where(PlanVersion.athlete_id == athlete_id)
            .order_by(desc(PlanVersion.version))
            .limit(1)
        )

    def get_plan(self, plan_id: str) -> PlanVersion | None:
        return self.db.get(PlanVersion, plan_id)

    def list_plans(self, athlete_id: str) -> list[PlanVersion]:
        return list(
            self.db.scalars(
                select(PlanVersion)
                .where(PlanVersion.athlete_id == athlete_id)
                .order_by(PlanVersion.version)
            ).all()
        )

    def create_plan(
        self,
        athlete_id: str,
        parent_plan_id: str | None,
        reason: str,
        world_state_hash: str,
        status: str,
        intent: dict,
        sessions: Iterable[SessionPlan],
        diff: dict,
    ) -> PlanVersion:
        latest = self.latest_plan(athlete_id)
        next_version = 1 if latest is None else latest.version + 1
        plan = PlanVersion(
            athlete_id=athlete_id,
            version=next_version,
            parent_plan_id=parent_plan_id,
            reason=reason,
            world_state_hash=world_state_hash,
            status=status,
            intent=intent,
            diff=diff,
        )
        self.db.add(plan)
        self.db.flush()
        for item in sessions:
            self.db.add(
                SessionModel(
                    plan_id=plan.id,
                    logical_key=item.logical_key,
                    session_type=item.session_type,
                    start_time=item.start_time,
                    duration_minutes=item.duration_minutes,
                    intended_load=item.intended_load,
                    intensity=item.intensity.value if hasattr(item.intensity, 'value') else str(item.intensity),
                    facility=item.facility,
                    status='planned',
                )
            )
        self.db.flush()
        return plan

    def update_plan_status(self, plan: PlanVersion, status: str) -> None:
        plan.status = status
        self.db.flush()

    def replace_constraint_results(self, plan_id: str, checks: list[dict]) -> None:
        existing = self.db.scalars(select(ConstraintResult).where(ConstraintResult.plan_id == plan_id)).all()
        for row in existing:
            self.db.delete(row)
        for c in checks:
            self.db.add(
                ConstraintResult(
                    plan_id=plan_id,
                    constraint_type=c['constraint_type'],
                    limit_value=c.get('limit'),
                    measured_value=c.get('measured_value'),
                    passed=c['passed'],
                    details=c.get('details', {}),
                )
            )
        self.db.flush()

    def add_verification(self, plan_id: str, state_snapshot: dict, passed: bool, violations: list[str]) -> VerificationRun:
        row = VerificationRun(
            plan_id=plan_id,
            state_snapshot=state_snapshot,
            passed=passed,
            violations=violations,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def add_agent_event(
        self, run_id: str, athlete_id: str, event_type: str, payload: dict, plan_id: str | None = None
    ) -> AgentEvent:
        row = AgentEvent(
            run_id=run_id,
            athlete_id=athlete_id,
            plan_id=plan_id,
            event_type=event_type,
            payload=payload,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_agent_events(self, athlete_id: str, run_id: str | None = None) -> list[AgentEvent]:
        stmt = select(AgentEvent).where(AgentEvent.athlete_id == athlete_id)
        if run_id:
            stmt = stmt.where(AgentEvent.run_id == run_id)
        return list(self.db.scalars(stmt.order_by(AgentEvent.created_at)).all())

    def get_tool_action_by_key(self, action_key: str) -> ToolAction | None:
        return self.db.scalar(select(ToolAction).where(ToolAction.action_key == action_key))

    def start_tool_action(
        self,
        athlete_id: str,
        plan_id: str | None,
        action_key: str,
        tool: str,
        arguments: dict,
    ) -> ToolAction:
        existing = self.get_tool_action_by_key(action_key)
        if existing:
            return existing
        row = ToolAction(
            athlete_id=athlete_id,
            plan_id=plan_id,
            action_key=action_key,
            tool=tool,
            arguments=arguments,
            result={},
            status='pending',
        )
        self.db.add(row)
        self.db.flush()
        return row

    def finish_tool_action(self, row: ToolAction, status: str, result: dict) -> ToolAction:
        row.status = status
        row.result = result
        row.finished_at = utcnow()
        self.db.flush()
        return row

    def add_web_evidence(
        self,
        athlete_id: str,
        plan_id: str | None,
        url: str,
        retrieved_at: datetime,
        field: str,
        value: dict,
        provenance: dict,
    ) -> WebEvidence:
        row = WebEvidence(
            athlete_id=athlete_id,
            plan_id=plan_id,
            url=url,
            retrieved_at=retrieved_at,
            field=field,
            value=value,
            provenance=provenance,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def upsert_facility_slot(
        self,
        facility: str,
        start_time: datetime,
        duration_minutes: int,
        available: bool,
        source_version: str,
        failure_mode: str | None = None,
    ) -> FacilitySlot:
        row = self.db.scalar(
            select(FacilitySlot).where(
                FacilitySlot.facility == facility,
                FacilitySlot.start_time == start_time,
            )
        )
        if not row:
            row = FacilitySlot(
                facility=facility,
                start_time=start_time,
                duration_minutes=duration_minutes,
                available=available,
                source_version=source_version,
                failure_mode=failure_mode,
            )
            self.db.add(row)
        else:
            row.duration_minutes = duration_minutes
            row.available = available
            row.source_version = source_version
            row.failure_mode = failure_mode
        self.db.flush()
        return row

    def facility_slot(self, facility: str, start_time: datetime) -> FacilitySlot | None:
        return self.db.scalar(
            select(FacilitySlot).where(
                FacilitySlot.facility == facility,
                FacilitySlot.start_time == start_time,
            )
        )

    def available_facility_slots(self, start: datetime, end: datetime) -> list[FacilitySlot]:
        return list(
            self.db.scalars(
                select(FacilitySlot)
                .where(FacilitySlot.start_time >= start, FacilitySlot.start_time <= end)
                .order_by(FacilitySlot.start_time, FacilitySlot.facility)
            ).all()
        )

    def create_booking(
        self,
        athlete_id: str,
        plan_id: str,
        session_id: str,
        action_key: str,
        facility: str,
        start_time: datetime,
        duration_minutes: int,
        status: str,
        confirmation_code: str | None,
    ) -> Booking:
        existing = self.db.scalar(select(Booking).where(Booking.action_key == action_key))
        if existing:
            return existing
        row = Booking(
            athlete_id=athlete_id,
            plan_id=plan_id,
            session_id=session_id,
            action_key=action_key,
            facility=facility,
            start_time=start_time,
            duration_minutes=duration_minutes,
            status=status,
            confirmation_code=confirmation_code,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_bookings(self, plan_id: str) -> list[Booking]:
        return list(self.db.scalars(select(Booking).where(Booking.plan_id == plan_id)).all())

    def create_calendar_entry(
        self,
        athlete_id: str,
        plan_id: str,
        session_id: str,
        action_key: str,
        title: str,
        start_time: datetime,
        duration_minutes: int,
        status: str = 'confirmed',
    ) -> CalendarEntry:
        existing = self.db.scalar(select(CalendarEntry).where(CalendarEntry.action_key == action_key))
        if existing:
            return existing
        row = CalendarEntry(
            athlete_id=athlete_id,
            plan_id=plan_id,
            session_id=session_id,
            action_key=action_key,
            external_id=f'cal-{uuid4().hex[:12]}',
            title=title,
            start_time=start_time,
            duration_minutes=duration_minutes,
            status=status,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_calendar_entries(self, plan_id: str) -> list[CalendarEntry]:
        return list(self.db.scalars(select(CalendarEntry).where(CalendarEntry.plan_id == plan_id)).all())
