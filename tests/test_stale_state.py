from simulator.scenarios import inject_stale_gps


def test_stale_source_blocks_certification(scenario):
    db, repo, athlete, orchestrator = scenario
    orchestrator.reconcile(athlete.id)
    version_before = repo.latest_plan(athlete.id).version

    inject_stale_gps(repo, athlete.id)
    db.commit()
    result = orchestrator.reconcile(athlete.id, 'GPS_UPDATED')

    assert result['status'] == 'STALE_STATE'
    assert 'STALE_SOURCE:gps' in result['error']
    assert repo.latest_plan(athlete.id).version == version_before
