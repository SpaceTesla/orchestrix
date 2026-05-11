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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
    )


settings = Settings()
