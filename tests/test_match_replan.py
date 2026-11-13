from simulator.scenarios import inject_wellness_drop, move_match_earlier


def test_match_change_invalidates_old_world_and_repairs_schedule(scenario):
    db, repo, athlete, orchestrator = scenario
    orchestrator.reconcile(athlete.id)
    inject_wellness_drop(repo, athlete.id)
    db.commit()
    orchestrator.reconcile(athlete.id, 'WELLNESS_CHANGED')
    old = repo.latest_plan(athlete.id)

    move_match_earlier(repo, athlete.id, 26)
    db.commit()
    result = orchestrator.reconcile(athlete.id, 'MATCH_CHANGED')
    new = repo.latest_plan(athlete.id)

    assert result['status'] == 'VERIFIED'
    assert result['plan_version'] == 3
    assert old.world_state_hash != new.world_state_hash
    assert 'tactical' in result['diff']['changed']
