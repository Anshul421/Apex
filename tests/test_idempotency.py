def test_reconcile_is_idempotent_when_world_did_not_change(scenario):
    db, repo, athlete, orchestrator = scenario
    first = orchestrator.reconcile(athlete.id)
    plan = repo.latest_plan(athlete.id)
    entries_before = len(repo.list_calendar_entries(plan.id))

    second = orchestrator.reconcile(athlete.id)

    assert first['status'] == 'VERIFIED'
    assert second['status'] == 'VERIFIED'
    assert second['noop'] is True
    assert repo.latest_plan(athlete.id).version == 1
    assert len(repo.list_calendar_entries(plan.id)) == entries_before
