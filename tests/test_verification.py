from app.planning.load_adapter import EvaluatorConfig, SyntheticLoadAdapter
from app.planning.verifier import PlanVerifier
from app.planning.world import build_world_snapshot
from app.config import get_settings


def test_independent_verifier_catches_constraint_breach(scenario):
    db, repo, athlete, orchestrator = scenario
    result = orchestrator.reconcile(athlete.id)
    assert result['status'] == 'VERIFIED'
    plan = repo.latest_plan(athlete.id)

    plan.sessions[0].intended_load = 1000
    db.flush()
    world = build_world_snapshot(repo, athlete.id, get_settings())
    verifier = PlanVerifier(db, SyntheticLoadAdapter(EvaluatorConfig.from_settings(get_settings())))
    report = verifier.verify(plan, world, include_action_state=False)

    assert report.passed is False
    assert any('DAILY_LOAD_EXCEEDED' in v or 'ROLLING_LOAD_EXCEEDED' in v for v in report.violations)
