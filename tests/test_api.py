from fastapi.testclient import TestClient
from app.main import app


def test_api_bootstrap_and_reconcile():
    client = TestClient(app)
    boot = client.post('/api/v1/simulator/bootstrap')
    assert boot.status_code == 201
    athlete_id = boot.json()['athlete']['id']

    run = client.post(
        f'/api/v1/athletes/{athlete_id}/autopilot/reconcile',
        json={'reason': 'USER_REQUEST'},
    )
    assert run.status_code == 200
    assert run.json()['status'] == 'VERIFIED'

    plan = client.get(f'/api/v1/athletes/{athlete_id}/plans/current')
    assert plan.status_code == 200
    assert plan.json()['version'] == 1
