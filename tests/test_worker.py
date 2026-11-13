from app.storage.models import Job
from app.worker import process_one


def test_background_worker_processes_reconcile_job(scenario):
    db, repo, athlete, orchestrator = scenario
    job = Job(
        job_type='athleteops.reconcile',
        payload={
            'athlete_id': athlete.id,
            'reason': 'ASYNC_TEST',
            'tenant_id': 'demo-tenant',
        },
        status='pending',
    )
    db.add(job)
    db.commit()
    job_id = job.id

    assert process_one() is True
    db.expire_all()
    refreshed = db.get(Job, job_id)
    assert refreshed.status == 'succeeded'
    assert refreshed.payload['result']['status'] == 'VERIFIED'
