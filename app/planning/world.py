from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.config import Settings
from app.storage.repository import AthleteRepository


class WorldSnapshot(BaseModel):
    athlete_id: str
    objective: str
    captured_at: datetime
    gps_version: str
    wellness_version: str
    fixture_version: str
    availability_version: str
    load_algorithm_version: str
    gps: dict[str, Any]
    wellness: dict[str, Any]
    availability: dict[str, Any]
    match: dict[str, Any]
    facility_slots: list[dict[str, Any]] = Field(default_factory=list)
    freshness: dict[str, bool]
    world_state_hash: str


def _age_minutes(now: datetime, observed_at: datetime) -> float:
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return (now - observed_at.astimezone(timezone.utc)).total_seconds() / 60.0


def build_world_snapshot(repo: AthleteRepository, athlete_id: str, settings: Settings, now: datetime | None = None) -> WorldSnapshot:
    now = now or datetime.now(timezone.utc)
    athlete = repo.get_athlete(athlete_id)
    if not athlete:
        raise ValueError(f'Athlete {athlete_id} not found')

    gps = repo.latest_observation(athlete_id, 'gps')
    wellness = repo.latest_observation(athlete_id, 'wellness')
    availability = repo.latest_observation(athlete_id, 'availability')
    match = repo.latest_match(athlete_id)
    if not all([gps, wellness, availability, match]):
        missing = [
            name
            for name, value in [('gps', gps), ('wellness', wellness), ('availability', availability), ('fixture', match)]
            if value is None
        ]
        raise ValueError(f'Missing required state: {", ".join(missing)}')

    # Freshness is checked separately from identity: unchanged data can still expire.
    freshness = {
        'gps': _age_minutes(now, gps.observed_at) <= settings.stale_gps_minutes,
        'wellness': _age_minutes(now, wellness.observed_at) <= settings.stale_wellness_minutes,
        'fixture': _age_minutes(now, match.created_at) <= settings.stale_fixture_minutes,
        'availability': _age_minutes(now, availability.observed_at) <= settings.stale_availability_minutes,
    }

    horizon_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    slots = repo.available_facility_slots(horizon_start - timedelta(days=1), horizon_start + timedelta(days=10))
    facility_slots = [
        {
            'facility': s.facility,
            'start_time': s.start_time.isoformat(),
            'duration_minutes': s.duration_minutes,
            'available': s.available,
            'source_version': s.source_version,
            'failure_mode': s.failure_mode,
        }
        for s in slots
    ]
    availability_version = availability.source_version
    if slots:
        latest_slot_version = max(s.source_version for s in slots)
        availability_version = f'{availability.source_version}|{latest_slot_version}'

    # Hash source versions rather than capture time so unchanged observations retain
    # the same identity. Producers must advance source_version when their data changes.
    fingerprint = {
        'gps': gps.source_version,
        'wellness': wellness.source_version,
        'fixture': match.source_version,
        'availability': availability_version,
        'load_algorithm': settings.load_algorithm_version,
    }
    world_hash = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode('utf-8')).hexdigest()

    return WorldSnapshot(
        athlete_id=athlete_id,
        objective=athlete.objective,
        captured_at=now,
        gps_version=gps.source_version,
        wellness_version=wellness.source_version,
        fixture_version=match.source_version,
        availability_version=availability_version,
        load_algorithm_version=settings.load_algorithm_version,
        gps=gps.payload,
        wellness=wellness.payload,
        availability=availability.payload,
        match={
            'match_id': match.id,
            'start_time': match.start_time.isoformat(),
            'venue': match.venue,
            'revision': match.revision,
            'source_version': match.source_version,
        },
        facility_slots=facility_slots,
        freshness=freshness,
        world_state_hash=world_hash,
    )
