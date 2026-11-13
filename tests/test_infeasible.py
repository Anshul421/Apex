from simulator.scenarios import inject_infeasible_availability


def test_infeasible_world_returns_infeasible_not_invented_plan(scenario):
    db, repo, athlete, orchestrator = scenario
    inject_infeasible_availability(repo, athlete.id)
    db.commit()

    result = orchestrator.reconcile(athlete.id, 'NO_AVAILABILITY')

    assert result['status'] == 'INFEASIBLE'
    assert result['conflicts']
    assert repo.latest_plan(athlete.id) is None
