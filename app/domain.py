from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field


class ObservationSource(StrEnum):
    GPS = 'gps'
    WELLNESS = 'wellness'
    AVAILABILITY = 'availability'
    FIXTURE = 'fixture'


class PlanStatus(StrEnum):
    PROPOSED = 'proposed'
    VERIFIED = 'verified'
    EXECUTING = 'executing'
    EXECUTED = 'executed'
    INVALIDATED = 'invalidated'
    INFEASIBLE = 'infeasible'
    FAILED = 'failed'


class SessionStatus(StrEnum):
    PLANNED = 'planned'
    SCHEDULED = 'scheduled'
    EXECUTED = 'executed'
    CANCELLED = 'cancelled'


class ActionStatus(StrEnum):
    PENDING = 'pending'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class Intensity(StrEnum):
    LOW = 'low'
    MODERATE = 'moderate'
    HIGH = 'high'
    FIXED = 'fixed'


class WebFact(BaseModel):
    field: str
    value: Any
    source_url: str
    retrieved_at: datetime
    provenance: dict[str, Any] = Field(default_factory=dict)


class TrainingIntent(BaseModel):
    priorities: list[str]
    preferred_session_types: list[str]
    reason: str


class SessionCandidate(BaseModel):
    logical_key: str
    session_type: str
    start_time: datetime
    duration_minutes: int
    intended_load: int
    intensity: Intensity
    facility: str | None = None
    preference_cost: int = 0

    @property
    def end_time(self) -> datetime:
        from datetime import timedelta
        return self.start_time + timedelta(minutes=self.duration_minutes)


class SessionPlan(BaseModel):
    logical_key: str
    session_type: str
    start_time: datetime
    duration_minutes: int
    intended_load: int
    intensity: Intensity
    facility: str | None = None

    @property
    def end_time(self) -> datetime:
        from datetime import timedelta
        return self.start_time + timedelta(minutes=self.duration_minutes)


class OptimizerResult(BaseModel):
    status: str
    sessions: list[SessionPlan] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    objective_value: int | None = None
    backend: str


class LoadConstraintResult(BaseModel):
    constraint_type: str
    limit: float | None = None
    measured_value: float | None = None
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class LoadEvaluation(BaseModel):
    metrics: dict[str, Any]
    constraints: list[LoadConstraintResult]
    violations: list[str]
    feasible: bool


class VerificationReport(BaseModel):
    passed: bool
    plan_id: str | None = None
    state_snapshot: dict[str, Any]
    checks: list[LoadConstraintResult]
    violations: list[str]
