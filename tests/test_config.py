import pytest
from pydantic import ValidationError

from orchestrix.config import Settings


def _settings(**overrides: object) -> Settings:
    base = {
        "postgres_user": "u",
        "postgres_password": "p",
        "postgres_db": "d",
        "database_url": "postgresql://u:p@localhost/d",
        "redis_host": "localhost",
        "redis_port": 6379,
        "redis_url": "redis://localhost:6379/0",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_reaper_threshold_must_exceed_job_timeout() -> None:
    with pytest.raises(ValidationError):
        _settings(job_timeout_seconds=60.0, reaper_threshold_seconds=60.0)


def test_valid_timeout_pair() -> None:
    settings = _settings(job_timeout_seconds=60.0, reaper_threshold_seconds=180.0)
    assert settings.job_timeout_seconds == 60.0
    assert settings.reaper_threshold_seconds == 180.0
