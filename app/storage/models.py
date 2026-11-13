from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Tenant(Base):
    __tablename__ = 'tenants'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), nullable=False, index=True)
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint('tenant_id', 'external_subject', name='uq_user_tenant_subject'),)


class Athlete(Base):
    __tablename__ = 'athletes'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), default='UTC', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    observations: Mapped[list['Observation']] = relationship(back_populates='athlete', cascade='all, delete-orphan')
    matches: Mapped[list['Match']] = relationship(back_populates='athlete', cascade='all, delete-orphan')
    plans: Mapped[list['PlanVersion']] = relationship(back_populates='athlete', cascade='all, delete-orphan')


class Observation(Base):
    __tablename__ = 'observations'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    athlete_id: Mapped[str] = mapped_column(ForeignKey('athletes.id'), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    freshness: Mapped[str] = mapped_column(String(32), default='fresh', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    athlete: Mapped[Athlete] = relationship(back_populates='observations')
    __table_args__ = (UniqueConstraint('athlete_id', 'source', 'source_version', name='uq_observation_source_version'),)


class Match(Base):
    __tablename__ = 'matches'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    athlete_id: Mapped[str] = mapped_column(ForeignKey('athletes.id'), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    venue: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    athlete: Mapped[Athlete] = relationship(back_populates='matches')


class PlanVersion(Base):
    __tablename__ = 'plan_versions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    athlete_id: Mapped[str] = mapped_column(ForeignKey('athletes.id'), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_plan_id: Mapped[str | None] = mapped_column(ForeignKey('plan_versions.id'))
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    world_state_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    intent: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    diff: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    athlete: Mapped[Athlete] = relationship(back_populates='plans')
    sessions: Mapped[list['Session']] = relationship(back_populates='plan', cascade='all, delete-orphan')
    constraint_results: Mapped[list['ConstraintResult']] = relationship(back_populates='plan', cascade='all, delete-orphan')
    tool_actions: Mapped[list['ToolAction']] = relationship(back_populates='plan')
    verification_runs: Mapped[list['VerificationRun']] = relationship(back_populates='plan', cascade='all, delete-orphan')

    __table_args__ = (UniqueConstraint('athlete_id', 'version', name='uq_plan_athlete_version'),)


class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey('plan_versions.id'), nullable=False, index=True)
    logical_key: Mapped[str] = mapped_column(String(128), nullable=False)
    session_type: Mapped[str] = mapped_column(String(128), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    intended_load: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity: Mapped[str] = mapped_column(String(32), nullable=False)
    facility: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default='planned', nullable=False)

    plan: Mapped[PlanVersion] = relationship(back_populates='sessions')
    __table_args__ = (UniqueConstraint('plan_id', 'logical_key', name='uq_session_plan_logical_key'),)


class ConstraintResult(Base):
    __tablename__ = 'constraint_results'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey('plan_versions.id'), nullable=False, index=True)
    constraint_type: Mapped[str] = mapped_column(String(128), nullable=False)
    limit_value: Mapped[float | None] = mapped_column(Float)
    measured_value: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    plan: Mapped[PlanVersion] = relationship(back_populates='constraint_results')


class ToolAction(Base):
    __tablename__ = 'tool_actions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    athlete_id: Mapped[str] = mapped_column(ForeignKey('athletes.id'), nullable=False, index=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey('plan_versions.id'), index=True)
    action_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    plan: Mapped[PlanVersion | None] = relationship(back_populates='tool_actions')


class WebEvidence(Base):
    __tablename__ = 'web_evidence'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    athlete_id: Mapped[str] = mapped_column(ForeignKey('athletes.id'), nullable=False, index=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey('plan_versions.id'), index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    field: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class VerificationRun(Base):
    __tablename__ = 'verification_runs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey('plan_versions.id'), nullable=False, index=True)
    state_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    violations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    plan: Mapped[PlanVersion] = relationship(back_populates='verification_runs')


class FacilitySlot(Base):
    __tablename__ = 'facility_slots'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    facility: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    failure_mode: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint('facility', 'start_time', name='uq_facility_slot'),)


class Booking(Base):
    __tablename__ = 'bookings'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    athlete_id: Mapped[str] = mapped_column(ForeignKey('athletes.id'), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey('plan_versions.id'), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'), nullable=False, index=True)
    action_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    facility: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmation_code: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CalendarEntry(Base):
    __tablename__ = 'calendar_entries'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    athlete_id: Mapped[str] = mapped_column(ForeignKey('athletes.id'), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey('plan_versions.id'), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'), nullable=False, index=True)
    action_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AgentEvent(Base):
    __tablename__ = 'agent_events'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    athlete_id: Mapped[str] = mapped_column(ForeignKey('athletes.id'), nullable=False, index=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey('plan_versions.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    job_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='pending', nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class MLExperiment(Base):
    __tablename__ = 'ml_experiments'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MLRun(Base):
    __tablename__ = 'ml_runs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey('ml_experiments.id'), nullable=False, index=True)
    run_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='running', index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    selected_model: Mapped[str | None] = mapped_column(String(128))
    decision: Mapped[str | None] = mapped_column(Text)


class MLModelVersion(Base):
    __tablename__ = 'ml_model_versions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey('ml_runs.id'), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default='candidate', index=True)
    alias: Mapped[str | None] = mapped_column(String(64), index=True)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    model_format: Mapped[str] = mapped_column(String(64), nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('name', 'version', name='uq_ml_model_name_version'),
        UniqueConstraint('name', 'alias', name='uq_ml_model_name_alias'),
    )


Index('ix_observation_athlete_source_time', Observation.athlete_id, Observation.source, Observation.observed_at)
Index('ix_plan_athlete_created', PlanVersion.athlete_id, PlanVersion.created_at)
Index('ix_tool_action_plan_status', ToolAction.plan_id, ToolAction.status)
Index('ix_ml_runs_experiment_started', MLRun.experiment_id, MLRun.started_at)
Index('ix_ml_model_versions_name_created', MLModelVersion.name, MLModelVersion.created_at)
