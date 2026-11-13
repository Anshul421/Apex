from simulator.scenarios import (
    inject_booking_conflict_for_plan,
    inject_wellness_drop,
    move_match_earlier,
)


def test_booking_conflict_is_persisted_and_repaired(scenario):
    db, repo, athlete, orchestrator = scenario
    orchestrator.reconcile(athlete.id)
    inject_wellness_drop(repo, athlete.id)
    db.commit()
    orchestrator.reconcile(athlete.id, 'WELLNESS_CHANGED')
    move_match_earlier(repo, athlete.id, 26)
    db.commit()
    orchestrator.reconcile(athlete.id, 'MATCH_CHANGED')

    before = repo.latest_plan(athlete.id)
    target = inject_booking_conflict_for_plan(repo, before.id)
    old_facility = target.facility
    db.commit()

    result = orchestrator.reconcile(athlete.id, 'BOOKING_CONFLICT_TEST')
    plans = repo.list_plans(athlete.id)
    final = repo.latest_plan(athlete.id)
    final_target = next(s for s in final.sessions if s.logical_key == target.logical_key)
    events = repo.list_agent_events(athlete.id, result['run_id'])

    assert result['status'] == 'VERIFIED'
    assert any(p.status == 'invalidated' for p in plans)
    assert any(e.event_type == 'BOOKING_FAILED' for e in events)
    assert final_target.facility != old_facility
    assert final_target.start_time == target.start_time
