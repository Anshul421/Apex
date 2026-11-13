from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from pydantic import BaseModel

from app.config import Settings
from app.domain import LoadConstraintResult, LoadEvaluation, SessionPlan


class EvaluatorConfig(BaseModel):
    algorithm_version: str
    max_daily_load: int
    max_rolling_7d_load: int
    high_intensity_match_buffer_hours: int
    moderate_match_buffer_hours: int
    moderate_buffer_min_load: int

    @classmethod
    def from_settings(cls, settings: Settings) -> 'EvaluatorConfig':
        return cls(
            algorithm_version=settings.load_algorithm_version,
            max_daily_load=settings.max_daily_load,
            max_rolling_7d_load=settings.max_rolling_7d_load,
            high_intensity_match_buffer_hours=settings.high_intensity_match_buffer_hours,
            moderate_match_buffer_hours=settings.moderate_match_buffer_hours,
            moderate_buffer_min_load=settings.moderate_buffer_min_load,
        )


class SyntheticLoadAdapter:
    """
    Replaceable deterministic load evaluator for the sandbox.

    The thresholds are evaluator configuration, not medical/injury thresholds. In the
    actual event this class should be replaced by the organizer-supplied load algorithm.
    """

    def __init__(self, config: EvaluatorConfig):
        self.config = config

    def evaluate(
        self,
        history: list[dict],
        candidate_plan: Iterable[SessionPlan],
        match_start: datetime,
    ) -> LoadEvaluation:
        if match_start.tzinfo is None:
            match_start = match_start.replace(tzinfo=timezone.utc)
        by_day: dict[date, int] = defaultdict(int)
        for item in history:
            day = date.fromisoformat(item['date'])
            by_day[day] += int(item['load'])

        sessions = list(candidate_plan)
        for session in sessions:
            by_day[session.start_time.date()] += int(session.intended_load)

        checks: list[LoadConstraintResult] = []
        violations: list[str] = []

        for day, load in sorted(by_day.items()):
            passed = load <= self.config.max_daily_load
            check = LoadConstraintResult(
                constraint_type='daily_load_max',
                limit=self.config.max_daily_load,
                measured_value=load,
                passed=passed,
                details={'date': day.isoformat()},
            )
            checks.append(check)
            if not passed:
                violations.append(f'DAILY_LOAD_EXCEEDED:{day.isoformat()}:{load}>{self.config.max_daily_load}')

        if by_day:
            start = min(by_day)
            end = max(by_day)
            cursor = start
            while cursor <= end:
                window_end = cursor + timedelta(days=6)
                rolling = sum(v for d, v in by_day.items() if cursor <= d <= window_end)
                passed = rolling <= self.config.max_rolling_7d_load
                checks.append(
                    LoadConstraintResult(
                        constraint_type='rolling_7d_load_max',
                        limit=self.config.max_rolling_7d_load,
                        measured_value=rolling,
                        passed=passed,
                        details={'window_start': cursor.isoformat(), 'window_end': window_end.isoformat()},
                    )
                )
                if not passed:
                    violations.append(
                        f'ROLLING_LOAD_EXCEEDED:{cursor.isoformat()}:{rolling}>{self.config.max_rolling_7d_load}'
                    )
                cursor += timedelta(days=1)

        buffer = timedelta(hours=self.config.high_intensity_match_buffer_hours)
        for session in sessions:
            if str(session.intensity) in {'high', 'Intensity.HIGH'}:
                delta = match_start - session.end_time
                passed = delta >= buffer or session.start_time >= match_start
                checks.append(
                    LoadConstraintResult(
                        constraint_type='high_intensity_match_buffer',
                        limit=self.config.high_intensity_match_buffer_hours,
                        measured_value=delta.total_seconds() / 3600.0,
                        passed=passed,
                        details={'logical_key': session.logical_key, 'match_start': match_start.isoformat()},
                    )
                )
                if not passed:
                    violations.append(
                        f'HIGH_INTENSITY_TOO_CLOSE_TO_MATCH:{session.logical_key}:{delta.total_seconds()/3600.0:.1f}h'
                    )
            elif str(session.intensity) in {'moderate', 'Intensity.MODERATE'} and session.intended_load >= self.config.moderate_buffer_min_load:
                delta = match_start - session.end_time
                moderate_buffer = timedelta(hours=self.config.moderate_match_buffer_hours)
                passed = delta >= moderate_buffer or session.start_time >= match_start
                checks.append(
                    LoadConstraintResult(
                        constraint_type='moderate_match_buffer',
                        limit=self.config.moderate_match_buffer_hours,
                        measured_value=delta.total_seconds() / 3600.0,
                        passed=passed,
                        details={'logical_key': session.logical_key, 'minimum_load': self.config.moderate_buffer_min_load},
                    )
                )
                if not passed:
                    violations.append(
                        f'MODERATE_TOO_CLOSE_TO_MATCH:{session.logical_key}:{delta.total_seconds()/3600.0:.1f}h'
                    )

        metrics = {
            'algorithm_version': self.config.algorithm_version,
            'daily_loads': {d.isoformat(): v for d, v in sorted(by_day.items())},
            'plan_total_load': sum(s.intended_load for s in sessions),
            'match_start': match_start.isoformat(),
        }
        return LoadEvaluation(
            metrics=metrics,
            constraints=checks,
            violations=violations,
            feasible=not violations,
        )
