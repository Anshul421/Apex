from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from app.domain import Intensity, SessionCandidate, SessionPlan, TrainingIntent
from app.planning.world import WorldSnapshot


@dataclass
class SessionRequirement:
    logical_key: str
    session_type: str
    duration_minutes: int
    intended_load: int
    intensity: Intensity
    preferred_day_offset_from_match: int
    preferred_time: time
    preferred_facility: str | None = None
    alternate_facilities: tuple[str, ...] = ()
    fixed: bool = False


class RuleBasedIntentProvider:
    """Development baseline that stands in for the later structured LLM intent node.

    It only produces semantic priorities. It never decides the final schedule or whether
    a schedule is valid; those decisions remain in the optimizer/verifier.
    """

    def create_intent(self, world: WorldSnapshot) -> TrainingIntent:
        recovery = float(world.wellness.get('recovery_score', 0.75))
        if recovery < 0.5:
            return TrainingIntent(
                priorities=[
                    'reduce immediate high-intensity load after recovery change',
                    'preserve competition preparation',
                    'minimize disruption to already planned sessions',
                ],
                preferred_session_types=['technical', 'recovery', 'moderate', 'primer'],
                reason='UPDATED_RECOVERY_STATE',
            )
        return TrainingIntent(
            priorities=[
                'preserve required training stimulus',
                'respect evaluator workload and match-spacing constraints',
                'minimize logistical disruption',
            ],
            preferred_session_types=['technical', 'high-intensity', 'recovery', 'tactical', 'primer'],
            reason='BASELINE_OR_WORLD_UPDATE',
        )


class CandidateGenerator:
    def build_requirements(self, world: WorldSnapshot, intent: TrainingIntent) -> list[SessionRequirement]:
        recovery = float(world.wellness.get('recovery_score', 0.75))
        requirements = [
            SessionRequirement('technical', 'Technical', 60, 300, Intensity.MODERATE, -6, time(17, 0)),
            SessionRequirement('high_1', 'High-intensity', 60, 450, Intensity.HIGH, -5, time(17, 0), 'Track A', ('Track D',)),
            SessionRequirement('recovery', 'Recovery', 45, 180, Intensity.LOW, -4, time(18, 0)),
            SessionRequirement('high_2', 'High-intensity', 60, 420, Intensity.HIGH, -3, time(17, 0), 'Track B', ('Track C', 'Track D')),
            SessionRequirement('tactical', 'Tactical', 60, 220, Intensity.MODERATE, -2, time(17, 0)),
            SessionRequirement('primer', 'Primer', 30, 120, Intensity.LOW, -1, time(10, 0)),
        ]
        if recovery < 0.5:
            # This is a synthetic scenario policy, not a medical rule. The semantic
            # intent changes; feasibility is still decided by the deterministic solver.
            requirements = [
                r if r.logical_key != 'high_2' else SessionRequirement(
                    'high_2', 'Recovery', 45, 180, Intensity.LOW, -3, time(17, 0), None, ()
                )
                for r in requirements
            ]
            requirements = [
                r if r.logical_key != 'tactical' else SessionRequirement(
                    'tactical', 'Moderate', 60, 340, Intensity.MODERATE, -2, time(17, 0), None, ()
                )
                for r in requirements
            ]
        return requirements

    def _availability_windows(self, world: WorldSnapshot) -> list[tuple[datetime, datetime]]:
        result: list[tuple[datetime, datetime]] = []
        for item in world.availability.get('windows', []):
            result.append((datetime.fromisoformat(item['start']), datetime.fromisoformat(item['end'])))
        return result

    def _within_availability(self, start: datetime, duration_minutes: int, windows: list[tuple[datetime, datetime]]) -> bool:
        end = start + timedelta(minutes=duration_minutes)
        return any(start >= w_start and end <= w_end for w_start, w_end in windows)

    def _facility_available(self, world: WorldSnapshot, facility: str, start: datetime, duration_minutes: int) -> bool:
        def _aware(value: datetime) -> datetime:
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        matching = [
            s for s in world.facility_slots
            if s['facility'] == facility and _aware(datetime.fromisoformat(s['start_time'])) == _aware(start)
        ]
        if not matching:
            return False
        slot = matching[0]
        return bool(slot['available']) and int(slot['duration_minutes']) >= duration_minutes

    def generate_candidates(
        self,
        world: WorldSnapshot,
        intent: TrainingIntent,
        parent_sessions: Iterable[SessionPlan] = (),
    ) -> dict[str, list[SessionCandidate]]:
        match_start = datetime.fromisoformat(world.match['start_time'])
        if match_start.tzinfo is None:
            match_start = match_start.replace(tzinfo=timezone.utc)
        windows = self._availability_windows(world)
        parent_by_key = {s.logical_key: s for s in parent_sessions}
        requirements = self.build_requirements(world, intent)
        output: dict[str, list[SessionCandidate]] = {}

        for req in requirements:
            candidates: dict[tuple, SessionCandidate] = {}
            preferred_date = (match_start + timedelta(days=req.preferred_day_offset_from_match)).date()
            day_options = [preferred_date]
            # One adjacent day is enough to demonstrate repair while keeping the search small.
            if req.logical_key in {'high_2', 'tactical', 'primer'}:
                day_options.append(preferred_date - timedelta(days=1))
                day_options.append(preferred_date + timedelta(days=1))

            times = [req.preferred_time]
            if req.logical_key in {'high_2', 'tactical'}:
                times.append(time(18, 30))

            facilities: tuple[str | None, ...]
            if req.preferred_facility:
                facilities = (req.preferred_facility, *req.alternate_facilities)
            else:
                facilities = (None,)

            # Freeze completed sessions. Future parent sessions are preserved when
            # they still satisfy raw availability and facility facts.
            parent = parent_by_key.get(req.logical_key)
            if parent and parent.start_time < world.captured_at:
                candidates[(parent.start_time, parent.facility)] = SessionCandidate(
                    logical_key=req.logical_key,
                    session_type=parent.session_type,
                    start_time=parent.start_time,
                    duration_minutes=parent.duration_minutes,
                    intended_load=parent.intended_load,
                    intensity=parent.intensity,
                    facility=parent.facility,
                    preference_cost=0,
                )
                output[req.logical_key] = list(candidates.values())
                continue
            elif parent:
                same_semantics = (
                    parent.session_type == req.session_type
                    and int(parent.intended_load) == int(req.intended_load)
                    and str(parent.intensity) in {req.intensity.value, str(req.intensity)}
                    and (req.preferred_facility is not None or parent.facility is None)
                )
                valid_parent = self._within_availability(parent.start_time, parent.duration_minutes, windows)
                if same_semantics and valid_parent:
                    if req.preferred_facility:
                        parent_facility_options = (parent.facility, req.preferred_facility, *req.alternate_facilities)
                        seen_facilities = set()
                        for facility in parent_facility_options:
                            if not facility or facility in seen_facilities:
                                continue
                            seen_facilities.add(facility)
                            if self._facility_available(world, facility, parent.start_time, parent.duration_minutes):
                                candidates[(parent.start_time, facility)] = SessionCandidate(
                                    logical_key=req.logical_key,
                                    session_type=req.session_type,
                                    start_time=parent.start_time,
                                    duration_minutes=req.duration_minutes,
                                    intended_load=req.intended_load,
                                    intensity=req.intensity,
                                    facility=facility,
                                    preference_cost=0 if facility == parent.facility else 8,
                                )
                    elif parent.facility is None:
                        candidates[(parent.start_time, None)] = SessionCandidate(
                            logical_key=req.logical_key,
                            session_type=req.session_type,
                            start_time=parent.start_time,
                            duration_minutes=req.duration_minutes,
                            intended_load=req.intended_load,
                            intensity=req.intensity,
                            facility=None,
                            preference_cost=0,
                        )

            for day in day_options:
                for t in times:
                    start = datetime.combine(day, t, tzinfo=match_start.tzinfo or timezone.utc)
                    if start < world.captured_at:
                        continue
                    if not self._within_availability(start, req.duration_minutes, windows):
                        continue
                    for facility in facilities:
                        if facility and not self._facility_available(world, facility, start, req.duration_minutes):
                            continue
                        day_penalty = abs((day - preferred_date).days) * 20
                        time_penalty = 0 if t == req.preferred_time else 5
                        facility_penalty = 0 if facility == req.preferred_facility else (8 if facility else 0)
                        candidates[(start, facility)] = SessionCandidate(
                            logical_key=req.logical_key,
                            session_type=req.session_type,
                            start_time=start,
                            duration_minutes=req.duration_minutes,
                            intended_load=req.intended_load,
                            intensity=req.intensity,
                            facility=facility,
                            preference_cost=day_penalty + time_penalty + facility_penalty,
                        )
            output[req.logical_key] = sorted(candidates.values(), key=lambda c: (c.preference_cost, c.start_time, c.facility or ''))

        return output
