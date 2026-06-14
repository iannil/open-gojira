import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///data/gojira.db"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    LIXINGER_TOKEN: str = ""
    SCHEDULER_ENABLED: bool = True
    RATE_LIMIT: str = "60/minute"
    # Autopilot Step 3: cockpit + plans UI is live, so the evaluator is
    # default-on. Override with `PLAN_EVALUATOR_ENABLED=false` to disable.
    PLAN_EVALUATOR_ENABLED: bool = True

    # ── Serenity research module (GLM) ────────────────────────────────────
    ZHIPU_API_KEY: str = ""
    ZHIPU_MODEL: str = "glm-4.7"
    ZHIPU_BASE_URL: str = ""
    SERENITY_MONTHLY_BUDGET_CNY: float = 100.0
    SERENITY_MAX_TOKENS: int = 16000
    SERENITY_MAX_SEARCHES: int = 30
    SERENITY_TIMEOUT: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  # 容忍 .env 里有未声明的字段 (避免 break 现有部署)
    )


settings = Settings()

if not settings.LIXINGER_TOKEN:
    logger.warning("LIXINGER_TOKEN is not set. API data endpoints will not work.")

if not settings.ZHIPU_API_KEY:
    logger.info("ZHIPU_API_KEY is not set. serenity research module will not work.")
