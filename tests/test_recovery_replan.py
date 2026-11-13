from simulator.scenarios import inject_wellness_drop


def test_wellness_change_creates_minimal_revision(scenario):
    db, repo, athlete, orchestrator = scenario
    first = orchestrator.reconcile(athlete.id)
    assert first['status'] == 'VERIFIED'

    inject_wellness_drop(repo, athlete.id)
    db.commit()
    second = orchestrator.reconcile(athlete.id, 'WELLNESS_CHANGED')

    assert second['status'] == 'VERIFIED'
    assert second['plan_version'] == 2
    assert set(second['diff']['changed']) == {'high_2', 'tactical'}
    assert {'technical', 'high_1', 'recovery', 'primer'} <= set(second['diff']['unchanged'])
