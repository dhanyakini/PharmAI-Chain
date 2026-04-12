"""Application configuration — loads from environment; fails fast on missing required values."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "sentinel-backend"
    env: str = "local"
    debug: bool = False
    secret_key: str = Field(..., min_length=16)
    access_token_expire_minutes: int = 1440
    jwt_algorithm: str = "HS256"

    # Admin seeding (dev convenience). For production, provide ADMIN_* env vars.
    seed_admin_defaults_in_local: bool = True
    seed_admin_username: str | None = None
    seed_admin_email: str | None = None
    seed_admin_password: str | None = None

    database_url: str = Field(..., description="async SQLAlchemy URL, e.g. postgresql+asyncpg://...")
    redis_url: str = Field(..., description="redis://host:port/db")

    groq_api_key: str = Field(
        default="",
        description="Groq API key for agentic LLM path; empty string falls back to deterministic policy.",
    )
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Live weather (OpenWeather Current Weather API). Optional: if unset, fallback ambient is used.
    openweather_api_key: str | None = None
    openweather_base_url: str = "https://api.openweathermap.org/data/2.5/weather"
    weather_cache_ttl_seconds: float = 300.0

    cors_origins: str = "http://localhost:5173"
    ws_origin: str = "http://localhost:5173"

    simulation_tick_seconds: float = 5.0
    simulated_minutes_per_tick: float = 15.0
    simulation_target_duration_seconds: float = 120.0
    temperature_threshold_f: float = 36.0
    target_temp_low_f: float = 35.0
    target_temp_high_f: float = 77.0

    thermal_coupling_per_hour: float = 0.35
    hvac_setpoint_f: float = 56.0
    hvac_strength_per_hour: float = 0.25

    supervisor_weight_safety: float = Field(0.5, ge=0.0, le=1.0)
    supervisor_weight_time: float = Field(0.3, ge=0.0, le=1.0)
    supervisor_weight_cost: float = Field(0.2, ge=0.0, le=1.0)

    log_level: str = "INFO"

    def supervisor_weights_ok(self) -> bool:
        s = (
            self.supervisor_weight_safety
            + self.supervisor_weight_time
            + self.supervisor_weight_cost
        )
        return abs(s - 1.0) < 1e-6

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()  # type: ignore[call-arg]
    if not s.supervisor_weights_ok():
        raise ValueError(
            "SUPERVISOR_WEIGHT_* must sum to 1.0 (safety + time + cost)."
        )
    return s


def clear_settings_cache() -> None:
    get_settings.cache_clear()
