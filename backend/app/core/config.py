from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "E-Magazyn ERP / WMS (Prototyp MVP)"
    DATABASE_URL: str = "sqlite:///./emagazyn_demo.db"

    JWT_SECRET_KEY: str = "dev-only-secret-change-before-vpn-deployment-32ch"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DEMO_MODE: bool = True
    SCALE_SIMULATOR_ENABLED: bool = True
    GUS_SIMULATOR_ENABLED: bool = True

    TERMINAL_IDLE_TIMEOUT_SECONDS: int = 300
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    return Settings()
