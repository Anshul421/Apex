from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "sqlite:///./athleteops_llm_test.db")
os.environ.setdefault("LLM_PROVIDER", "rule_based")

from app.agent.intent_provider import (
    FallbackChainIntentProvider,
    GroqStructuredIntentProvider,
    IntentDecision,
    IntentProviderError,
    OpenRouterStructuredIntentProvider,
    RuleBasedIntentAdapter,
    StructuredIntentOutput,
    _intent_context,
    build_intent_provider,
)
from app.config import Settings
from app.domain import TrainingIntent
from app.planning.world import WorldSnapshot


class FakeResponse:
    def __init__(self, data: dict[str, Any], status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            request = httpx.Request('POST', 'https://example.test/chat/completions')
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f'HTTP {self.status_code}',
                request=request,
                response=response,
            )

    def json(self) -> dict[str, Any]:
        return self._data


class FakeClient:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, json: dict[str, Any]):
        self.calls.append((url, json))
        if not self.responses:
            raise AssertionError('No fake response configured')
        return self.responses.pop(0)


def make_world() -> WorldSnapshot:
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    return WorldSnapshot(
        athlete_id='athlete-test',
        objective='prepare for competition while respecting recovery state',
        captured_at=now,
        gps_version='gps:1',
        wellness_version='wellness:2',
        fixture_version='fixture:1',
        availability_version='availability:1|facility:1',
        load_algorithm_version='load:v1',
        gps={
            'history': [
                {'date': '2026-09-11', 'load': 90},
                {'date': '2026-09-12', 'load': 100},
            ]
        },
        wellness={
            'recovery_score': 0.42,
            'fatigue': 4,
            'soreness': 3,
            'sleep_quality': 2,
        },
        availability={
            'windows': [
                {
                    'start': '2026-09-14T09:00:00+00:00',
                    'end': '2026-09-14T20:00:00+00:00',
                }
            ]
        },
        match={
            'start_time': '2026-09-19T16:00:00+00:00',
            'revision': 1,
        },
        facility_slots=[
            {
                'facility': 'Track A',
                'start_time': '2026-09-14T17:00:00+00:00',
                'duration_minutes': 60,
                'available': True,
            }
        ],
        freshness={
            'gps': True,
            'wellness': True,
            'fixture': True,
            'availability': True,
        },
        world_state_hash='hash-test',
    )


def valid_content(reason: str = 'UPDATED_RECOVERY_STATE') -> str:
    return json.dumps(
        {
            'priorities': [
                'reduce immediate high-intensity exposure',
                'preserve competition preparation',
            ],
            'preferred_session_types': [
                'technical',
                'recovery',
                'moderate',
                'primer',
            ],
            'reason': reason,
        }
    )


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        '_env_file': None,
        'llm_timeout_seconds': 2.0,
        'llm_max_retries': 0,
        'llm_fallback_to_rules': False,
    }
    values.update(overrides)
    return Settings(**values)


def test_openrouter_free_router_returns_structured_intent_and_actual_model():
    fake = FakeClient(
        [
            FakeResponse(
                {
                    'model': 'qwen/example-free-model',
                    'choices': [
                        {
                            'message': {
                                'content': valid_content(),
                            }
                        }
                    ],
                }
            )
        ]
    )
    cfg = settings(
        llm_provider='openrouter',
        openrouter_api_key='test-openrouter-key',
        openrouter_model='openrouter/free',
    )
    provider = OpenRouterStructuredIntentProvider(cfg, client=fake)

    decision = provider.create_intent(make_world(), 'WELLNESS_CHANGED')

    assert decision.provider == 'openrouter'
    assert decision.model == 'qwen/example-free-model'
    assert decision.intent.reason == 'UPDATED_RECOVERY_STATE'
    assert decision.fallback_used is False

    _, payload = fake.calls[0]
    assert payload['model'] == 'openrouter/free'
    assert payload['provider']['require_parameters'] is True
    assert payload['provider']['allow_fallbacks'] is True
    assert payload['response_format']['type'] == 'json_schema'
    assert payload['response_format']['json_schema']['strict'] is True
    assert 'tools' not in payload

    user_context = json.loads(payload['messages'][1]['content'])
    assert 'availability' not in user_context
    assert 'facility_slots' not in user_context
    assert 'load_limit' not in user_context


def test_groq_provider_uses_structured_schema_and_configured_model():
    fake = FakeClient(
        [
            FakeResponse(
                {
                    'model': 'openai/gpt-oss-20b',
                    'choices': [
                        {
                            'message': {
                                'content': valid_content('BASELINE_OR_WORLD_UPDATE'),
                            }
                        }
                    ],
                }
            )
        ]
    )
    cfg = settings(
        llm_provider='groq',
        groq_api_key='test-groq-key',
        groq_model='openai/gpt-oss-20b',
    )
    provider = GroqStructuredIntentProvider(cfg, client=fake)

    decision = provider.create_intent(make_world(), 'USER_REQUEST')

    assert decision.provider == 'groq'
    assert decision.model == 'openai/gpt-oss-20b'
    assert decision.intent.reason == 'BASELINE_OR_WORLD_UPDATE'

    _, payload = fake.calls[0]
    assert payload['model'] == 'openai/gpt-oss-20b'
    assert payload['response_format']['json_schema']['strict'] is True
    assert 'provider' not in payload


def test_external_provider_cannot_add_schedule_or_load_fields():
    fake = FakeClient(
        [
            FakeResponse(
                {
                    'model': 'openai/gpt-oss-20b',
                    'choices': [
                        {
                            'message': {
                                'content': json.dumps(
                                    {
                                        'priorities': ['preserve readiness'],
                                        'preferred_session_types': ['recovery'],
                                        'reason': 'TEST_REASON',
                                        'start_time': '2026-09-14T17:00:00Z',
                                        'intended_load': 999,
                                    }
                                )
                            }
                        }
                    ],
                }
            )
        ]
    )
    cfg = settings(
        llm_provider='groq',
        groq_api_key='test-groq-key',
    )
    provider = GroqStructuredIntentProvider(cfg, client=fake)

    with pytest.raises(IntentProviderError) as exc_info:
        provider.create_intent(make_world(), 'USER_REQUEST')

    assert exc_info.value.code == 'GROQ_STRUCTURED_OUTPUT_INVALID'


def test_context_never_exposes_deterministic_scheduling_inputs():
    context = _intent_context(make_world(), 'MATCH_CHANGED')

    assert 'availability' not in context
    assert 'facility_slots' not in context
    assert 'max_daily_load' not in context
    assert 'max_rolling_7d_load' not in context
    assert 'load_algorithm_version' not in context


def test_fallback_chain_uses_second_external_provider_and_records_primary_error():
    class AlwaysFails:
        def create_intent(self, world, reason):
            raise IntentProviderError('OPENROUTER_INTENT_REQUEST_FAILED_HTTP_429', 'rate limited')

    class SecondaryWorks:
        def create_intent(self, world, reason):
            return IntentDecision(
                intent=TrainingIntent(
                    priorities=['preserve competition preparation'],
                    preferred_session_types=['technical'],
                    reason='SECONDARY_PROVIDER_USED',
                ),
                provider='groq',
                model='openai/gpt-oss-20b',
            )

    chain = FallbackChainIntentProvider(
        providers=[AlwaysFails(), SecondaryWorks()],
        fallback=None,
    )

    decision = chain.create_intent(make_world(), 'USER_REQUEST')

    assert decision.provider == 'groq'
    assert decision.fallback_used is True
    assert decision.primary_error_code == 'OPENROUTER_INTENT_REQUEST_FAILED_HTTP_429'


def test_fallback_chain_can_end_in_deterministic_rules():
    class AlwaysFails:
        def create_intent(self, world, reason):
            raise IntentProviderError('GROQ_INTENT_REQUEST_FAILED_HTTP_429', 'rate limited')

    chain = FallbackChainIntentProvider(
        providers=[AlwaysFails()],
        fallback=RuleBasedIntentAdapter(),
    )

    decision = chain.create_intent(make_world(), 'USER_REQUEST')

    assert decision.provider == 'rule_based'
    assert decision.fallback_used is True
    assert decision.primary_error_code == 'GROQ_INTENT_REQUEST_FAILED_HTTP_429'


def test_build_provider_supports_rule_based_openrouter_groq_and_auto():
    rule = build_intent_provider(settings(llm_provider='rule_based'))
    assert isinstance(rule, RuleBasedIntentAdapter)

    openrouter = build_intent_provider(
        settings(
            llm_provider='openrouter',
            openrouter_api_key='test-openrouter-key',
            llm_fallback_to_rules=True,
        )
    )
    assert isinstance(openrouter, FallbackChainIntentProvider)

    groq = build_intent_provider(
        settings(
            llm_provider='groq',
            groq_api_key='test-groq-key',
            llm_fallback_to_rules=True,
        )
    )
    assert isinstance(groq, FallbackChainIntentProvider)

    auto = build_intent_provider(
        settings(
            llm_provider='auto',
            openrouter_api_key='test-openrouter-key',
            groq_api_key='test-groq-key',
            llm_fallback_to_rules=True,
        )
    )
    assert isinstance(auto, FallbackChainIntentProvider)
    assert len(auto.providers) == 2


def test_schema_itself_forbids_extra_authority_fields():
    with pytest.raises(ValidationError):
        StructuredIntentOutput.model_validate(
            {
                'priorities': ['preserve readiness'],
                'preferred_session_types': ['recovery'],
                'reason': 'VALID_REASON',
                'facility': 'Track A',
            }
        )
