import logging

from pydantic_settings import BaseSettings

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

    model_config = {"env_file": ".env"}


settings = Settings()

if not settings.LIXINGER_TOKEN:
    logger.warning("LIXINGER_TOKEN is not set. API data endpoints will not work.")
