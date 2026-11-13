import os
from pathlib import Path

TEST_DB = '/tmp/athleteops_pytest.db'
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['ENVIRONMENT'] = 'test'
os.environ['AUTH_MODE'] = 'dev'
os.environ['AUTO_EXECUTE_ACTIONS'] = 'true'

import pytest

from app.storage.database import Base, engine, SessionLocal
from app.storage.repository import AthleteRepository
from app.config import get_settings
from app.agent.orchestrator import AthleteOpsOrchestrator
from simulator.scenarios import seed_demo_scenario


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def scenario():
    db = SessionLocal()
    repo = AthleteRepository(db)
    repo.ensure_identity('demo-tenant', 'demo-user')
    athlete = seed_demo_scenario(repo, 'demo-tenant')
    db.commit()
    orchestrator = AthleteOpsOrchestrator(repo, get_settings())
    try:
        yield db, repo, athlete, orchestrator
    finally:
        db.close()
