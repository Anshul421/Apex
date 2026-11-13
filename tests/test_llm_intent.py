from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent.intent_provider import (
    IntentDecision,
    IntentProviderError,
    OpenAIStructuredIntentProvider,
    ResilientIntentProvider,
    RuleBasedIntentAdapter,
    StructuredIntentOutput,
)
from app.config import Settings, get_settings
from app.domain import TrainingIntent
from app.planning.world import build_world_snapshot


class FakeResponses:
    def __init__(self, parsed: StructuredIntentOutput):
        self.parsed = parsed
        self.last_kwargs = None

    def parse(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(
                            type="output_text",
                            parsed=self.parsed,
                        )
                    ],
                )
            ]
        )


class FakeOpenAIClient:
    def __init__(self, parsed: StructuredIntentOutput):
        self.responses = FakeResponses(parsed)


def test_structured_llm_intent_returns_only_bounded_semantics(scenario):
    _, repo, athlete, _ = scenario

    settings = Settings(
        llm_provider="openai",
        openai_api_key="test-key",
        openai_model="test-model",
    )
    world = build_world_snapshot(repo, athlete.id, settings)

    parsed = StructuredIntentOutput(
        priorities=[
            "prioritize recovery-sensitive preparation",
            "preserve competition readiness",
        ],
        preferred_session_types=[
            "recovery",
            "technical",
            "primer",
        ],
        reason="RECOVERY_STATE_CHANGED",
    )
    client = FakeOpenAIClient(parsed)
    provider = OpenAIStructuredIntentProvider(
        settings,
        client=client,
    )

    decision = provider.create_intent(
        world,
        "WELLNESS_CHANGED",
    )

    assert decision.provider == "openai"
    assert decision.model == "test-model"
    assert decision.fallback_used is False
    assert decision.intent.reason == "RECOVERY_STATE_CHANGED"

    call = client.responses.last_kwargs
    assert call is not None
    assert call["model"] == "test-model"
    assert call["text_format"] is StructuredIntentOutput

    sent_context = json.loads(call["input"])

    # The LLM sees semantic observations, but not the deterministic scheduling
    # surfaces that select exact slots/facilities.
    assert "wellness" in sent_context
    assert "upcoming_match" in sent_context
    assert "availability" not in sent_context
    assert "facility_slots" not in sent_context


def test_structured_intent_schema_rejects_schedule_and_load_authority():
    with pytest.raises(ValidationError):
        StructuredIntentOutput.model_validate(
            {
                "priorities": ["preserve readiness"],
                "preferred_session_types": ["recovery"],
                "reason": "TEST_REASON",
                "start_time": "2026-09-14T17:00:00Z",
                "intended_load": 999,
            }
        )


class FailingIntentProvider:
    def create_intent(self, world, reason):
        raise IntentProviderError(
            "TEST_PRIMARY_FAILURE",
            "Synthetic provider failure",
        )


def test_llm_failure_explicitly_falls_back_to_rules(scenario):
    _, repo, athlete, _ = scenario
    settings = get_settings()
    world = build_world_snapshot(repo, athlete.id, settings)

    provider = ResilientIntentProvider(
        primary=FailingIntentProvider(),
        fallback=RuleBasedIntentAdapter(),
    )

    decision = provider.create_intent(
        world,
        "USER_REQUEST",
    )

    assert decision.provider == "rule_based"
    assert decision.fallback_used is True
    assert decision.primary_error_code == "TEST_PRIMARY_FAILURE"
    assert decision.intent.priorities


def test_graph_accepts_llm_semantics_but_keeps_optimizer_and_verifier_authority(
    scenario,
    monkeypatch,
):
    _, repo, athlete, orchestrator = scenario

    class FakeSemanticProvider:
        def create_intent(self, world, reason):
            return IntentDecision(
                intent=TrainingIntent(
                    priorities=[
                        "prefer recovery-oriented preparation",
                    ],
                    preferred_session_types=[
                        "recovery",
                    ],
                    reason="LLM_SEMANTIC_TEST",
                ),
                provider="fake_llm",
                model="fake-model",
            )

    monkeypatch.setattr(
        "app.agent.nodes.build_intent_provider",
        lambda settings: FakeSemanticProvider(),
    )

    result = orchestrator.reconcile(
        athlete.id,
        "USER_REQUEST",
    )

    assert result["status"] == "VERIFIED"
    assert result["optimizer_backend"] == "ortools_cp_sat"
    assert result["verification"]["passed"] is True

    plan = repo.latest_plan(athlete.id)
    assert plan is not None
    assert plan.intent["reason"] == "LLM_SEMANTIC_TEST"

    # Deterministic verification still produced the constraint evidence.
    constraint_types = {
        check["constraint_type"]
        for check in result["verification"]["checks"]
    }
    assert "daily_load_max" in constraint_types
    assert "rolling_7d_load_max" in constraint_types
    assert "session_overlap" in constraint_types


def test_llm_failure_without_fallback_ends_graph_cleanly(
    scenario,
    monkeypatch,
):
    _, _, athlete, orchestrator = scenario

    monkeypatch.setattr(
        "app.agent.nodes.build_intent_provider",
        lambda settings: FailingIntentProvider(),
    )

    result = orchestrator.reconcile(
        athlete.id,
        "USER_REQUEST",
    )

    assert result["status"] == "FAILED"
    assert result["error"] == (
        "INTENT_PROVIDER_FAILED:TEST_PRIMARY_FAILURE"
    )
