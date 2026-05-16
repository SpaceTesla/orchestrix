from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_db: str
    database_url: str

    redis_host: str
    redis_port: int
    redis_url: str

    # Phase 6: single tenant; Phase 7 adds explicit tenant selection per request.
    default_tenant_name: str = "default"

    retry_base_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 300.0

    job_timeout_seconds: float = 60.0
    reaper_threshold_seconds: float = 180.0
    reaper_interval_seconds: float = 30.0
    reaper_batch_size: int = 100

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    metrics_worker_port: int = 9090

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_reaper_vs_job_timeout(self) -> Self:
        if self.reaper_threshold_seconds <= self.job_timeout_seconds:
            raise ValueError(
                "reaper_threshold_seconds must be greater than job_timeout_seconds "
                f"(got reaper={self.reaper_threshold_seconds}, "
                f"job_timeout={self.job_timeout_seconds})"
            )
        return self


settings = Settings()
