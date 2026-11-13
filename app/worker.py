from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from app.agent.orchestrator import AthleteOpsOrchestrator
from app.config import get_settings
from app.storage.database import SessionLocal
from app.storage.models import Job
from app.storage.repository import AthleteRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('athleteops.worker')
settings = get_settings()


def process_one() -> bool:
    with SessionLocal() as db:
        job = db.scalar(
            select(Job)
            .where(Job.status == 'pending', Job.available_at <= datetime.now(timezone.utc))
            .order_by(Job.created_at)
            .limit(1)
        )
        if not job:
            return False
        job.status = 'running'
        job.attempts += 1
        db.commit()
        try:
            repo = AthleteRepository(db)
            if job.job_type == 'athleteops.reconcile':
                result = AthleteOpsOrchestrator(repo, settings).reconcile(
                    job.payload['athlete_id'], job.payload.get('reason', 'ASYNC_JOB')
                )
            else:
                raise ValueError(f'Unknown job type: {job.job_type}')
            job.payload = {**job.payload, 'result': result}
            job.status = 'succeeded'
            job.last_error = None
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job.id)
            job.last_error = str(exc)
            if job.attempts >= job.max_attempts:
                job.status = 'dead_letter'
            else:
                job.status = 'pending'
                job.available_at = datetime.now(timezone.utc) + timedelta(seconds=2 ** job.attempts)
            db.commit()
            logger.exception('job_failed id=%s', job.id)
        return True


def main() -> None:
    logger.info('worker_started')
    while True:
        if not process_one():
            time.sleep(1)


if __name__ == '__main__':
    main()
