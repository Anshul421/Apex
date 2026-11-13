from __future__ import annotations

from sqlalchemy import desc, select

from app.storage.models import CalendarEntry, PlanVersion, Session as SessionModel
from app.storage.repository import AthleteRepository
from app.tools.idempotency import action_key


class SandboxCalendarTool:
    """State-changing calendar adapter with idempotent receipts.

    A logical training session keeps one external calendar event across plan revisions;
    revisions update that event rather than duplicating it.
    """

    name = 'sandbox_calendar'

    def __init__(self, repo: AthleteRepository):
        self.repo = repo

    def _existing_logical_event(self, athlete_id: str, logical_key: str) -> CalendarEntry | None:
        return self.repo.db.scalar(
            select(CalendarEntry)
            .join(SessionModel, CalendarEntry.session_id == SessionModel.id)
            .where(CalendarEntry.athlete_id == athlete_id, SessionModel.logical_key == logical_key)
            .order_by(desc(CalendarEntry.created_at))
            .limit(1)
        )

    def upsert_session(self, athlete_id: str, plan: PlanVersion, session: SessionModel) -> dict:
        key = action_key(plan.version, 'calendar_upsert', session.logical_key, session.start_time.isoformat())
        existing_action = self.repo.get_tool_action_by_key(key)
        if existing_action and existing_action.status == 'succeeded':
            return existing_action.result

        action = self.repo.start_tool_action(
            athlete_id=athlete_id,
            plan_id=plan.id,
            action_key=key,
            tool=self.name,
            arguments={
                'logical_key': session.logical_key,
                'start_time': session.start_time.isoformat(),
                'duration_minutes': session.duration_minutes,
            },
        )
        existing_event = self._existing_logical_event(athlete_id, session.logical_key)
        if existing_event:
            existing_event.plan_id = plan.id
            existing_event.session_id = session.id
            existing_event.action_key = key
            existing_event.title = f'AthleteOps: {session.session_type}'
            existing_event.start_time = session.start_time
            existing_event.duration_minutes = session.duration_minutes
            existing_event.status = 'confirmed'
            entry = existing_event
            operation = 'updated'
            self.repo.db.flush()
        else:
            entry = self.repo.create_calendar_entry(
                athlete_id=athlete_id,
                plan_id=plan.id,
                session_id=session.id,
                action_key=key,
                title=f'AthleteOps: {session.session_type}',
                start_time=session.start_time,
                duration_minutes=session.duration_minutes,
            )
            operation = 'created'

        result = {'status': 'confirmed', 'operation': operation, 'calendar_event_id': entry.external_id}
        self.repo.finish_tool_action(action, 'succeeded', result)
        return result
