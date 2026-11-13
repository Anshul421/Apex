from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.agent.prompts import INTENT_SYSTEM_PROMPT
from app.config import Settings
from app.domain import TrainingIntent
from app.planning.candidate_generator import RuleBasedIntentProvider
from app.planning.world import WorldSnapshot


AllowedSessionType = Literal[
    "technical",
    "high-intensity",
    "recovery",
    "tactical",
    "primer",
    "moderate",
]


class StructuredIntentOutput(BaseModel):
    """The only schema an external LLM may return.

    Scheduling, loads, facilities, tool authority, feasibility and verification
    are intentionally absent and remain deterministic elsewhere in the backend.
    """

    model_config = ConfigDict(extra="forbid")

    priorities: list[str]
    preferred_session_types: list[AllowedSessionType]
    reason: str

    @field_validator("priorities")
    @classmethod
    def validate_priorities(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if not 1 <= len(cleaned) <= 5:
            raise ValueError("priorities must contain between 1 and 5 items")
        if any(len(item) > 160 for item in cleaned):
            raise ValueError("priority text is too long")
        return cleaned

    @field_validator("preferred_session_types")
    @classmethod
    def validate_preferred_types(
        cls,
        value: list[AllowedSessionType],
    ) -> list[AllowedSessionType]:
        deduped = list(dict.fromkeys(value))
        if not 1 <= len(deduped) <= 6:
            raise ValueError(
                "preferred_session_types must contain between 1 and 6 items"
            )
        return deduped

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        import re

        value = value.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", value):
            raise ValueError(
                "reason must be a 3-64 character UPPER_SNAKE_CASE code"
            )
        return value


@dataclass(frozen=True)
class IntentDecision:
    intent: TrainingIntent
    provider: str
    model: str | None
    fallback_used: bool = False
    primary_error_code: str | None = None


class IntentProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class IntentProvider(Protocol):
    def create_intent(
        self,
        world: WorldSnapshot,
        reason: str,
    ) -> IntentDecision:
        ...


class RuleBasedIntentAdapter:
    """Adapter around the deterministic semantic baseline."""

    def __init__(
        self,
        provider: RuleBasedIntentProvider | None = None,
    ):
        self.provider = provider or RuleBasedIntentProvider()

    def create_intent(
        self,
        world: WorldSnapshot,
        reason: str,
    ) -> IntentDecision:
        del reason
        intent = self.provider.create_intent(world)
        return IntentDecision(
            intent=intent,
            provider="rule_based",
            model=None,
        )


def _intent_context(
    world: WorldSnapshot,
    reason: str,
) -> dict[str, Any]:
    """Bounded semantic context only.

    Availability windows and facility slots are deliberately withheld because
    they belong to deterministic candidate generation and scheduling.
    """

    history = world.gps.get("history", [])
    recent_training: list[dict[str, Any]] = []
    for item in history[-7:]:
        if not isinstance(item, dict):
            continue
        recent_training.append(
            {
                "date": item.get("date"),
                "load": item.get("load"),
            }
        )

    wellness = {
        key: world.wellness.get(key)
        for key in (
            "recovery_score",
            "fatigue",
            "soreness",
            "sleep_quality",
        )
        if key in world.wellness
    }

    return {
        "trigger_reason": reason,
        "athlete_objective": world.objective,
        "wellness": wellness,
        "recent_training_observations": recent_training,
        "upcoming_match": {
            "start_time": world.match.get("start_time"),
            "revision": world.match.get("revision"),
        },
        "source_freshness": world.freshness,
        "allowed_preferred_session_types": [
            "technical",
            "high-intensity",
            "recovery",
            "tactical",
            "primer",
            "moderate",
        ],
    }


def _schema_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "athleteops_intent",
            "strict": True,
            "schema": StructuredIntentOutput.model_json_schema(),
        },
    }


class OpenAICompatibleStructuredIntentProvider:
    """Structured intent over an OpenAI-compatible HTTP endpoint.

    This class intentionally uses httpx directly rather than the OpenAI SDK,
    so using OpenRouter or Groq does not require an OpenAI API account.
    """

    provider_name: str = "compatible"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        client: Any | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") + "/"
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, int(max_retries))
        self._client = client
        self.extra_headers = extra_headers or {}
        self.extra_body = extra_body or {}

    def _error_prefix(self) -> str:
        return self.provider_name.upper().replace("-", "_")

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise IntentProviderError(
                f"{self._error_prefix()}_API_KEY_MISSING",
                f"{self.provider_name} API key is not configured.",
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        return self._client

    def _request_payload(
        self,
        world: WorldSnapshot,
        reason: str,
    ) -> dict[str, Any]:
        context = _intent_context(world, reason)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": INTENT_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        context,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ),
                },
            ],
            "response_format": _schema_response_format(),
        }
        payload.update(self.extra_body)
        return payload

    def _perform_request(self, client: Any, payload: dict[str, Any]) -> Any:
        last_exc: Exception | None = None
        attempts = self.max_retries + 1

        for _ in range(attempts):
            try:
                response = client.post(
                    "chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                return response
            except Exception as exc:  # network/HTTP errors are normalized below
                last_exc = exc

        assert last_exc is not None
        raise last_exc

    def create_intent(
        self,
        world: WorldSnapshot,
        reason: str,
    ) -> IntentDecision:
        client = self._client_or_raise()
        payload = self._request_payload(world, reason)

        try:
            response = self._perform_request(client, payload)
            data = response.json()
        except IntentProviderError:
            raise
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            suffix = f"_HTTP_{status_code}" if status_code is not None else ""
            raise IntentProviderError(
                f"{self._error_prefix()}_INTENT_REQUEST_FAILED{suffix}",
                f"Structured intent request failed: {type(exc).__name__}",
            ) from exc

        try:
            choices = data["choices"]
            message = choices[0]["message"]
            content = message["content"]
            if isinstance(content, list):
                # Defensive normalization for providers returning content parts.
                content = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                )
            parsed = StructuredIntentOutput.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValidationError, ValueError) as exc:
            raise IntentProviderError(
                f"{self._error_prefix()}_STRUCTURED_OUTPUT_INVALID",
                "Provider response did not match the structured intent schema.",
            ) from exc

        intent = TrainingIntent(
            priorities=list(parsed.priorities),
            preferred_session_types=[
                str(item)
                for item in parsed.preferred_session_types
            ],
            reason=parsed.reason,
        )

        actual_model = data.get("model") or self.model
        return IntentDecision(
            intent=intent,
            provider=self.provider_name,
            model=str(actual_model) if actual_model is not None else None,
        )


class OpenAIStructuredIntentProvider(OpenAICompatibleStructuredIntentProvider):
    """Legacy OpenAI endpoint support retained for backward compatibility."""

    provider_name = "openai"

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
    ):
        super().__init__(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            client=client,
        )


class OpenRouterStructuredIntentProvider(OpenAICompatibleStructuredIntentProvider):
    provider_name = "openrouter"

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
    ):
        headers: dict[str, str] = {}
        if settings.openrouter_app_url:
            headers["HTTP-Referer"] = settings.openrouter_app_url
        if settings.openrouter_app_name:
            headers["X-Title"] = settings.openrouter_app_name

        super().__init__(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            client=client,
            extra_headers=headers,
            extra_body={
                "provider": {
                    "require_parameters": True,
                    "allow_fallbacks": True,
                }
            },
        )


class GroqStructuredIntentProvider(OpenAICompatibleStructuredIntentProvider):
    provider_name = "groq"

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
    ):
        super().__init__(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.groq_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            client=client,
        )


class FallbackChainIntentProvider:
    """Try providers in order, optionally ending in deterministic rules."""

    def __init__(
        self,
        providers: Sequence[IntentProvider],
        fallback: IntentProvider | None = None,
    ):
        self.providers = list(providers)
        self.fallback = fallback

    def create_intent(
        self,
        world: WorldSnapshot,
        reason: str,
    ) -> IntentDecision:
        errors: list[str] = []

        for provider in self.providers:
            try:
                decision = provider.create_intent(world, reason)
                if not errors:
                    return decision
                return IntentDecision(
                    intent=decision.intent,
                    provider=decision.provider,
                    model=decision.model,
                    fallback_used=True,
                    primary_error_code="|".join(errors),
                )
            except IntentProviderError as exc:
                errors.append(exc.code)

        if self.fallback is not None:
            decision = self.fallback.create_intent(world, reason)
            return IntentDecision(
                intent=decision.intent,
                provider=decision.provider,
                model=decision.model,
                fallback_used=bool(errors),
                primary_error_code="|".join(errors) if errors else None,
            )

        raise IntentProviderError(
            "LLM_INTENT_ALL_PROVIDERS_FAILED",
            "All configured external intent providers failed: "
            + ("|".join(errors) if errors else "none configured"),
        )


# Backward-compatible alias for any older imports.
ResilientIntentProvider = FallbackChainIntentProvider


def _with_rule_fallback(
    primary: IntentProvider,
    settings: Settings,
    baseline: IntentProvider,
) -> IntentProvider:
    return FallbackChainIntentProvider(
        providers=[primary],
        fallback=baseline if settings.llm_fallback_to_rules else None,
    )


def build_intent_provider(settings: Settings) -> IntentProvider:
    provider = settings.llm_provider.strip().lower()
    baseline: IntentProvider = RuleBasedIntentAdapter()

    if provider == "rule_based":
        return baseline

    if provider == "openai":
        return _with_rule_fallback(
            OpenAIStructuredIntentProvider(settings),
            settings,
            baseline,
        )

    if provider == "openrouter":
        return _with_rule_fallback(
            OpenRouterStructuredIntentProvider(settings),
            settings,
            baseline,
        )

    if provider == "groq":
        return _with_rule_fallback(
            GroqStructuredIntentProvider(settings),
            settings,
            baseline,
        )

    if provider in {"auto", "auto_free"}:
        external: list[IntentProvider] = []
        if settings.openrouter_api_key:
            external.append(OpenRouterStructuredIntentProvider(settings))
        if settings.groq_api_key:
            external.append(GroqStructuredIntentProvider(settings))

        if not external:
            if settings.llm_fallback_to_rules:
                return baseline
            raise IntentProviderError(
                "LLM_API_KEY_MISSING",
                "LLM_PROVIDER=auto requires OPENROUTER_API_KEY or GROQ_API_KEY.",
            )

        return FallbackChainIntentProvider(
            providers=external,
            fallback=baseline if settings.llm_fallback_to_rules else None,
        )

    raise IntentProviderError(
        "UNSUPPORTED_LLM_PROVIDER",
        f"Unsupported LLM_PROVIDER={settings.llm_provider!r}.",
    )
