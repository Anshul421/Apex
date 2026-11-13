def test_baseline_produces_verified_plan_and_actions(scenario):
    db, repo, athlete, orchestrator = scenario
    result = orchestrator.reconcile(athlete.id)

    assert result['status'] == 'VERIFIED'
    assert result['plan_version'] == 1
    plan = repo.latest_plan(athlete.id)
    assert plan.status == 'executed'
    assert len(plan.sessions) == 6
    assert all(v.passed for v in plan.verification_runs if v.id)
    assert len(repo.list_calendar_entries(plan.id)) == 6
    assert len(repo.list_bookings(plan.id)) == 2
