from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'AthleteOps Autopilot API'
    environment: str = 'development'
    api_prefix: str = '/api/v1'

    # Production should point to PostgreSQL. Tests override this with SQLite.
    database_url: str = Field(
        default='postgresql+psycopg://athleteops:athleteops@localhost:5432/athleteops'
    )

    # dev = X-Dev-* headers; oidc = bearer JWT verified through JWKS.
    auth_mode: str = 'dev'
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None

    default_tenant_id: str = 'demo-tenant'
    default_subject: str = 'demo-user'

    # Synthetic evaluator rules. These are sandbox rules, not medical thresholds.
    load_algorithm_version: str = 'load:v1'
    max_daily_load: int = 700
    max_rolling_7d_load: int = 2400
    high_intensity_match_buffer_hours: int = 36
    moderate_match_buffer_hours: int = 24
    moderate_buffer_min_load: int = 300
    stale_gps_minutes: int = 24 * 60
    stale_wellness_minutes: int = 24 * 60
    stale_fixture_minutes: int = 7 * 24 * 60
    stale_availability_minutes: int = 12 * 60

    # Planner and action loop guards.
    max_replan_attempts: int = 3
    auto_execute_actions: bool = True

    # Structured semantic intent provider.
    # Supported: rule_based, openrouter, groq, auto/auto_free.
    llm_provider: str = 'rule_based'
    llm_timeout_seconds: float = 15.0
    llm_max_retries: int = 1
    llm_fallback_to_rules: bool = True

    # OpenRouter: OpenAI-compatible routing across many model providers.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = 'https://openrouter.ai/api/v1'
    openrouter_model: str = 'openrouter/free'
    openrouter_app_url: str | None = None
    openrouter_app_name: str = 'APEX AthleteOps'

    # Groq: direct free-tier-capable OpenAI-compatible inference.
    groq_api_key: str | None = None
    groq_base_url: str = 'https://api.groq.com/openai/v1'
    groq_model: str = 'openai/gpt-oss-20b'

    # Legacy OpenAI fields are retained only so old .env files remain harmless.
    openai_api_key: str | None = None
    openai_base_url: str = 'https://api.openai.com/v1'
    openai_model: str = 'gpt-5.6-luna'

    google_calendar_credentials_json: str | None = None

    # ML baseline and experiment tracking.
    ml_artifact_dir: str = './artifacts/ml'
    ml_experiment_name: str = 'athlete-recovery-intervention-baseline'
    ml_model_name: str = 'athlete-recovery-intervention'
    ml_dataset_name: str = 'synthetic-athlete-recovery-v1'
    ml_feature_schema_version: str = 'recovery-features:v1'
    ml_random_seed: int = 42
    ml_min_auc_lift: float = 0.02

    # PostgreSQL connection-pool defaults for local/dev and production.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 1800

    # Observability.
    log_level: str = 'INFO'
    otel_service_name: str = 'athleteops-api'

    @field_validator('database_url', mode='before')
    @classmethod
    def normalize_database_url(cls, value):
        if isinstance(value, str) and value.startswith('postgres://'):
            return 'postgresql+psycopg://' + value[len('postgres://'):]
        if isinstance(value, str) and value.startswith('postgresql://'):
            return 'postgresql+psycopg://' + value[len('postgresql://'):]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
