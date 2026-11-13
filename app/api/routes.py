from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.orchestrator import AthleteOpsOrchestrator
from app.api.auth import AuthContext, get_auth_context
from app.api.schemas import AthleteCreate, AthleteOut, RunRequest
from app.config import Settings, get_settings
from app.storage.database import get_db
from app.storage.models import Job, PlanVersion
from app.storage.repository import AthleteRepository
from simulator.scenarios import (
    inject_booking_conflict_for_plan,
    inject_infeasible_availability,
    inject_stale_gps,
    inject_wellness_drop,
    move_match_earlier,
    seed_demo_scenario,
)

router = APIRouter()


def _repo(db: Session, auth: AuthContext) -> AthleteRepository:
    repo = AthleteRepository(db)
    repo.ensure_identity(auth.tenant_id, auth.subject)
    return repo


def _require_athlete(repo: AthleteRepository, athlete_id: str, auth: AuthContext):
    athlete = repo.get_athlete(athlete_id, auth.tenant_id)
    if not athlete:
        raise HTTPException(status_code=404, detail='Athlete not found')
    return athlete


def _plan_payload(plan: PlanVersion) -> dict:
    return {
        'id': plan.id,
        'athlete_id': plan.athlete_id,
        'version': plan.version,
        'parent_plan_id': plan.parent_plan_id,
        'reason': plan.reason,
        'created_at': plan.created_at,
        'world_state_hash': plan.world_state_hash,
        'status': plan.status,
        'intent': plan.intent,
        'diff': plan.diff,
        'sessions': [
            {
                'id': s.id,
                'logical_key': s.logical_key,
                'session_type': s.session_type,
                'start_time': s.start_time,
                'duration_minutes': s.duration_minutes,
                'intended_load': s.intended_load,
                'intensity': s.intensity,
                'facility': s.facility,
                'status': s.status,
            }
            for s in sorted(plan.sessions, key=lambda x: x.start_time)
        ],
        'constraints': [
            {
                'constraint_type': c.constraint_type,
                'limit': c.limit_value,
                'measured_value': c.measured_value,
                'passed': c.passed,
                'details': c.details,
            }
            for c in plan.constraint_results
        ],
        'verification_runs': [
            {
                'id': v.id,
                'passed': v.passed,
                'violations': v.violations,
                'state_snapshot': v.state_snapshot,
                'created_at': v.created_at,
            }
            for v in plan.verification_runs
        ],
    }


@router.get('/health/live')
def live():
    return {'status': 'ok'}


@router.get('/health/ready')
def ready(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {'status': 'ready'}


@router.post('/athletes', response_model=AthleteOut, status_code=status.HTTP_201_CREATED)
def create_athlete(
    payload: AthleteCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    athlete = repo.create_athlete(auth.tenant_id, payload.name, payload.objective, payload.timezone_name)
    db.commit()
    return athlete


@router.get('/athletes/{athlete_id}', response_model=AthleteOut)
def get_athlete(
    athlete_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    return _require_athlete(repo, athlete_id, auth)


@router.post('/simulator/bootstrap', status_code=status.HTTP_201_CREATED)
def bootstrap_demo(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    athlete = seed_demo_scenario(repo, auth.tenant_id)
    db.commit()
    return {'athlete': AthleteOut.model_validate(athlete).model_dump(mode='json')}


@router.post('/athletes/{athlete_id}/autopilot/reconcile')
def reconcile(
    athlete_id: str,
    payload: RunRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    return AthleteOpsOrchestrator(repo, settings).reconcile(athlete_id, payload.reason)


@router.post('/athletes/{athlete_id}/autopilot/reconcile-async', status_code=status.HTTP_202_ACCEPTED)
def reconcile_async(
    athlete_id: str,
    payload: RunRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    job = Job(
        job_type='athleteops.reconcile',
        payload={'athlete_id': athlete_id, 'reason': payload.reason, 'tenant_id': auth.tenant_id},
        status='pending',
    )
    db.add(job)
    db.commit()
    return {'job_id': job.id, 'status': job.status}


@router.get('/jobs/{job_id}')
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    if job.payload.get('tenant_id') != auth.tenant_id:
        raise HTTPException(status_code=404, detail='Job not found')
    return {
        'id': job.id,
        'job_type': job.job_type,
        'status': job.status,
        'attempts': job.attempts,
        'last_error': job.last_error,
        'result': job.payload.get('result'),
    }


@router.get('/athletes/{athlete_id}/plans')
def list_plans(
    athlete_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    return [_plan_payload(p) for p in repo.list_plans(athlete_id)]


@router.get('/athletes/{athlete_id}/plans/current')
def current_plan(
    athlete_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    plan = repo.latest_plan(athlete_id)
    if not plan:
        raise HTTPException(status_code=404, detail='No plan exists')
    return _plan_payload(plan)


@router.get('/athletes/{athlete_id}/events')
def agent_events(
    athlete_id: str,
    run_id: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    return [
        {
            'id': e.id,
            'run_id': e.run_id,
            'plan_id': e.plan_id,
            'event_type': e.event_type,
            'payload': e.payload,
            'created_at': e.created_at,
        }
        for e in repo.list_agent_events(athlete_id, run_id)
    ]


@router.post('/simulator/athletes/{athlete_id}/inject/wellness-drop')
def simulator_wellness_drop(
    athlete_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    obs = inject_wellness_drop(repo, athlete_id)
    db.commit()
    return {'source_version': obs.source_version, 'payload': obs.payload}


@router.post('/simulator/athletes/{athlete_id}/inject/match-move')
def simulator_match_move(
    athlete_id: str,
    hours: int = 26,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    match = move_match_earlier(repo, athlete_id, hours)
    db.commit()
    return {'source_version': match.source_version, 'start_time': match.start_time}


@router.post('/simulator/athletes/{athlete_id}/inject/booking-conflict')
def simulator_booking_conflict(
    athlete_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    plan = repo.latest_plan(athlete_id)
    if not plan:
        raise HTTPException(status_code=409, detail='Run the agent once before injecting a booking conflict')
    target = inject_booking_conflict_for_plan(repo, plan.id)
    db.commit()
    return {'target_session': target.logical_key, 'facility': target.facility, 'start_time': target.start_time}


@router.post('/simulator/athletes/{athlete_id}/inject/stale-gps')
def simulator_stale_gps(
    athlete_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    obs = inject_stale_gps(repo, athlete_id)
    db.commit()
    return {'source_version': obs.source_version, 'observed_at': obs.observed_at}


@router.post('/simulator/athletes/{athlete_id}/inject/infeasible')
def simulator_infeasible(
    athlete_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    repo = _repo(db, auth)
    _require_athlete(repo, athlete_id, auth)
    obs = inject_infeasible_availability(repo, athlete_id)
    db.commit()
    return {'source_version': obs.source_version}
