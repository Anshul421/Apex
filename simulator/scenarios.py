from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.storage.repository import AthleteRepository


def _next_weekday(base: datetime, weekday: int, hour: int, minute: int = 0) -> datetime:
    days = (weekday - base.weekday()) % 7
    if days == 0 and base.time() >= time(hour, minute):
        days = 7
    target = (base + timedelta(days=days)).date()
    return datetime.combine(target, time(hour, minute), tzinfo=base.tzinfo)


def seed_demo_scenario(repo: AthleteRepository, tenant_id: str, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    athlete = repo.create_athlete(
        tenant_id=tenant_id,
        name='Demo Athlete',
        objective=(
            "Maintain competition readiness for the upcoming match, preserve the required "
            "training stimulus, respect supplied workload/scheduling constraints, execute "
            "required bookings/calendar actions, and adapt when the world changes."
        ),
        timezone_name='UTC',
    )

    match_start = _next_weekday(now, 6, 18, 0)  # Sunday 18:00 UTC
    # Ensure enough planning horizon for the six training sessions.
    if match_start - now < timedelta(days=6):
        match_start += timedelta(days=7)

    gps_history = []
    for i in range(7, 0, -1):
        day = (now.date() - timedelta(days=i)).isoformat()
        gps_history.append({'date': day, 'load': 80 + (i % 3) * 10, 'distance_m': 3500 + i * 120})

    repo.add_observation(
        athlete.id,
        'gps',
        now,
        'gps:1',
        {'history': gps_history, 'summary': {'source': 'synthetic GPS feed'}},
    )
    repo.add_observation(
        athlete.id,
        'wellness',
        now,
        'wellness:1',
        {
            'recovery_score': 0.78,
            'fatigue': 2,
            'soreness': 2,
            'sleep_quality': 4,
            'source': 'synthetic wellness feed',
        },
    )

    windows = []
    for offset in range(-1, 9):
        day = (now + timedelta(days=offset)).date()
        start = datetime.combine(day, time(8, 0), tzinfo=timezone.utc)
        end = datetime.combine(day, time(21, 0), tzinfo=timezone.utc)
        windows.append({'start': start.isoformat(), 'end': end.isoformat()})
    repo.add_observation(
        athlete.id,
        'availability',
        now,
        'availability:1',
        {'windows': windows, 'source': 'synthetic athlete calendar availability'},
    )
    repo.add_match(
        athlete.id,
        match_start,
        'Arena Alpha',
        revision=1,
        source_version='fixture:1',
    )

    # Facility discovery data. The booking write path may still fail even when
    # discovery reports availability, which is important for the agent demo.
    for day_offset in range(-7, 2):
        day = (match_start + timedelta(days=day_offset)).date()
        for slot_time in (time(17, 0), time(18, 30)):
            start = datetime.combine(day, slot_time, tzinfo=timezone.utc)
            for facility in ('Track A', 'Track B', 'Track C', 'Track D'):
                repo.upsert_facility_slot(
                    facility=facility,
                    start_time=start,
                    duration_minutes=90,
                    available=True,
                    source_version='facility:1',
                )
    repo.db.flush()
    return athlete


def inject_wellness_drop(repo: AthleteRepository, athlete_id: str, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    latest = repo.latest_observation(athlete_id, 'wellness')
    version = 1
    if latest:
        try:
            version = int(latest.source_version.split(':')[-1]) + 1
        except Exception:
            version = 2
    return repo.add_observation(
        athlete_id,
        'wellness',
        now,
        f'wellness:{version}',
        {
            'recovery_score': 0.35,
            'fatigue': 4,
            'soreness': 4,
            'sleep_quality': 2,
            'source': 'synthetic changed wellness feed',
        },
    )


def move_match_earlier(repo: AthleteRepository, athlete_id: str, hours: int = 26):
    current = repo.latest_match(athlete_id)
    if not current:
        raise ValueError('No match exists')
    return repo.add_match(
        athlete_id,
        current.start_time - timedelta(hours=hours),
        current.venue,
        revision=current.revision + 1,
        source_version=f'fixture:{current.revision + 1}',
    )


def inject_booking_conflict_for_plan(repo: AthleteRepository, plan_id: str):
    plan = repo.get_plan(plan_id)
    if not plan:
        raise ValueError('Plan not found')
    facility_sessions = [s for s in plan.sessions if s.facility]
    if not facility_sessions:
        raise ValueError('Plan has no facility session')
    # Prefer high_2 because it is the most useful demo repair; otherwise use the last facility session.
    target = next((s for s in facility_sessions if s.logical_key == 'high_2'), facility_sessions[-1])
    slot = repo.facility_slot(target.facility, target.start_time)
    if not slot:
        raise ValueError('Facility slot not found')
    # Force the next write to exercise failure recovery rather than reusing a
    # previously successful reservation receipt.
    from sqlalchemy import select
    from app.storage.models import Booking
    for booking in repo.db.scalars(
        select(Booking).where(
            Booking.athlete_id == plan.athlete_id,
            Booking.facility == target.facility,
            Booking.start_time == target.start_time,
            Booking.status == 'confirmed',
        )
    ).all():
        booking.status = 'cancelled'
    slot.available = True
    slot.failure_mode = 'conflict_once'
    repo.db.flush()
    return target


def inject_stale_gps(repo: AthleteRepository, athlete_id: str, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    latest = repo.latest_observation(athlete_id, 'gps')
    version = 2
    history = []
    if latest:
        history = latest.payload.get('history', [])
        try:
            version = int(latest.source_version.split(':')[-1]) + 1
        except Exception:
            version = 2
    return repo.add_observation(
        athlete_id,
        'gps',
        now - timedelta(days=3),
        f'gps:{version}',
        {'history': history, 'source': 'synthetic stale GPS feed'},
        freshness='stale',
    )


def inject_infeasible_availability(repo: AthleteRepository, athlete_id: str, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    latest = repo.latest_observation(athlete_id, 'availability')
    version = 2
    if latest:
        try:
            version = int(latest.source_version.split(':')[-1]) + 1
        except Exception:
            version = 2
    return repo.add_observation(
        athlete_id,
        'availability',
        now,
        f'availability:{version}',
        {'windows': [], 'source': 'synthetic no-availability scenario'},
    )
