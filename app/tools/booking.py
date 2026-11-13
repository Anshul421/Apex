from __future__ import annotations

from uuid import uuid4
from sqlalchemy import desc, select

from app.storage.models import Booking, PlanVersion, Session as SessionModel
from app.storage.repository import AthleteRepository
from app.tools.idempotency import action_key


class BookingConflict(Exception):
    def __init__(self, facility: str, start_time: str):
        super().__init__(f'SLOT_UNAVAILABLE:{facility}:{start_time}')
        self.facility = facility
        self.start_time = start_time


class SandboxBookingTool:
    name = 'sandbox_booking'

    def __init__(self, repo: AthleteRepository):
        self.repo = repo

    def _existing_confirmed_reservation(self, athlete_id: str, facility: str, start_time):
        return self.repo.db.scalar(
            select(Booking)
            .where(
                Booking.athlete_id == athlete_id,
                Booking.facility == facility,
                Booking.start_time == start_time,
                Booking.status == 'confirmed',
            )
            .order_by(desc(Booking.created_at))
            .limit(1)
        )

    def reserve(self, athlete_id: str, plan: PlanVersion, session: SessionModel) -> dict:
        if not session.facility:
            return {'status': 'not_required'}
        key = action_key(plan.version, 'facility_book', session.facility, session.start_time.isoformat())
        existing = self.repo.get_tool_action_by_key(key)
        if existing and existing.status == 'succeeded':
            return existing.result

        action = self.repo.start_tool_action(
            athlete_id=athlete_id,
            plan_id=plan.id,
            action_key=key,
            tool=self.name,
            arguments={
                'facility': session.facility,
                'start_time': session.start_time.isoformat(),
                'duration_minutes': session.duration_minutes,
            },
        )

        # If a previous plan already booked this exact slot, carry the reservation
        # forward rather than making a duplicate external booking.
        prior = self._existing_confirmed_reservation(athlete_id, session.facility, session.start_time)
        if prior:
            booking = self.repo.create_booking(
                athlete_id=athlete_id,
                plan_id=plan.id,
                session_id=session.id,
                action_key=key,
                facility=session.facility,
                start_time=session.start_time,
                duration_minutes=session.duration_minutes,
                status='confirmed',
                confirmation_code=prior.confirmation_code,
            )
            result = {
                'status': 'confirmed',
                'operation': 'reused',
                'confirmation_code': booking.confirmation_code,
            }
            self.repo.finish_tool_action(action, 'succeeded', result)
            return result

        slot = self.repo.facility_slot(session.facility, session.start_time)
        if not slot or not slot.available:
            result = {'status': 'failed', 'code': 'SLOT_UNAVAILABLE'}
            self.repo.finish_tool_action(action, 'failed', result)
            raise BookingConflict(session.facility, session.start_time.isoformat())

        if slot.failure_mode == 'conflict_once':
            # Discovery said available, but the write fails. Persist the observed
            # environment change so the next planning pass cannot select it again.
            slot.available = False
            slot.failure_mode = None
            prefix = slot.source_version.split(':')[0]
            try:
                n = int(slot.source_version.split(':')[-1]) + 1
            except Exception:
                n = 2
            slot.source_version = f'{prefix}:{n}'
            result = {'status': 'failed', 'code': 'SLOT_ALREADY_BOOKED'}
            self.repo.finish_tool_action(action, 'failed', result)
            self.repo.db.flush()
            raise BookingConflict(session.facility, session.start_time.isoformat())

        confirmation = f'R-{uuid4().hex[:8].upper()}'
        booking = self.repo.create_booking(
            athlete_id=athlete_id,
            plan_id=plan.id,
            session_id=session.id,
            action_key=key,
            facility=session.facility,
            start_time=session.start_time,
            duration_minutes=session.duration_minutes,
            status='confirmed',
            confirmation_code=confirmation,
        )
        result = {'status': 'confirmed', 'operation': 'created', 'confirmation_code': booking.confirmation_code}
        self.repo.finish_tool_action(action, 'succeeded', result)
        self.repo.db.flush()
        return result
