from functools import lru_cache
from typing import Any, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DOCUMENTED_GEMINI_VISION_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
)

YOU_CAM_CATEGORIES = (
    "upper_body",
    "lower_body",
    "full_body",
    "shoes",
    "outer",
    "auto",
)

# Closet categories → YouCam cloth-v4 names, plus the official identifiers.
YOU_CAM_CATEGORY_ALIASES = {
    "upper_body": "upper_body",
    "top": "upper_body",
    "upper": "upper_body",
    "lower_body": "lower_body",
    "bottom": "lower_body",
    "lower": "lower_body",
    "full_body": "full_body",
    "dress": "full_body",
    "full": "full_body",
    "outer": "outer",
    "outerwear": "outer",
    "shoes": "shoes",
    "footwear": "shoes",
    "auto": "auto",
}


def _youcam_env(default: Any, *names: str) -> Any:
    # Docs and Railway use YOU_CAM_*; pydantic's default for youcam_* is YOUCAM_*.
    return Field(default=default, validation_alias=AliasChoices(*names))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_name: str = "Closest Chemistry"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="",
        description="SQLAlchemy URL. Use postgresql+psycopg:// for Supabase/Postgres.",
    )
    database_ssl_require: bool = True

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_storage_bucket: str = "closest-chemistry-private"

    jwt_issuer: str = ""
    auth_mode: Literal["single", "session"] = "single"
    single_owner_id: str = "local"
    cors_origins: str = "http://localhost:3000"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_prompt_version: str = "garment-extract-v1"

    youcam_api_key: str = _youcam_env("", "YOU_CAM_API_KEY", "YOUCAM_API_KEY", "youcam_api_key")
    youcam_base_url: str = _youcam_env(
        "https://yce-api-01.makeupar.com", "YOU_CAM_BASE_URL", "YOUCAM_BASE_URL", "youcam_base_url"
    )
    youcam_engine_version: str = _youcam_env(
        "cloth-v4", "YOU_CAM_ENGINE_VERSION", "YOUCAM_ENGINE_VERSION", "youcam_engine_version"
    )
    youcam_unit_cost: int = _youcam_env(2, "YOU_CAM_UNIT_COST", "YOUCAM_UNIT_COST", "youcam_unit_cost")
    youcam_enabled_categories: str = _youcam_env(
        "", "YOU_CAM_ENABLED_CATEGORIES", "YOUCAM_ENABLED_CATEGORIES", "youcam_enabled_categories"
    )
    youcam_poll_interval_seconds: int = _youcam_env(
        10, "YOU_CAM_POLL_INTERVAL_SECONDS", "YOUCAM_POLL_INTERVAL_SECONDS", "youcam_poll_interval_seconds"
    )
    youcam_poll_timeout_seconds: int = _youcam_env(
        180, "YOU_CAM_POLL_TIMEOUT_SECONDS", "YOUCAM_POLL_TIMEOUT_SECONDS", "youcam_poll_timeout_seconds"
    )
    youcam_webhook_secret: str = _youcam_env(
        "", "YOU_CAM_WEBHOOK_SECRET", "YOUCAM_WEBHOOK_SECRET", "youcam_webhook_secret"
    )

    daily_spend_cap_units: int = 40
    per_user_concurrency: int = 2
    max_provider_attempts: int = 3
    job_lease_seconds: int = 90
    job_heartbeat_seconds: int = 20
    job_max_attempts: int = 5

    max_outfit_photos: int = 15
    max_upload_bytes: int = 10 * 1024 * 1024
    min_image_side: int = 128
    max_image_side: int = 4096
    max_candidates: int = 10
    min_candidates: int = 4
    retention_days: int = 90

    local_storage_dir: str = ".local_storage"
    frontend_origin: str = "http://localhost:3000"

    @field_validator("gemini_model")
    @classmethod
    def validate_gemini_model(cls, value: str) -> str:
        if value and value not in DOCUMENTED_GEMINI_VISION_MODELS:
            raise ValueError(
                "GEMINI_MODEL must be a documented Gemini vision identifier. "
                f"Allowed: {', '.join(DOCUMENTED_GEMINI_VISION_MODELS)}"
            )
        return value

    @field_validator("youcam_api_key", "youcam_enabled_categories", "youcam_base_url", "youcam_webhook_secret", mode="before")
    @classmethod
    def strip_youcam_strings(cls, value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip().strip("\"'")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        raw = [item.strip().rstrip("/") for item in self.cors_origins.split(",") if item.strip()]
        if self.frontend_origin:
            raw.append(self.frontend_origin.strip().rstrip("/"))
        expanded: list[str] = []
        for origin in raw:
            expanded.append(origin)
            if "://localhost" in origin:
                expanded.append(origin.replace("://localhost", "://127.0.0.1"))
            elif "://127.0.0.1" in origin:
                expanded.append(origin.replace("://127.0.0.1", "://localhost"))
        seen: set[str] = set()
        out: list[str] = []
        for origin in expanded:
            if origin and origin not in seen:
                seen.add(origin)
                out.append(origin)
        return out

    @property
    def youcam_category_list(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in (self.youcam_enabled_categories or "").split(","):
            mapped = YOU_CAM_CATEGORY_ALIASES.get(item.strip().strip("\"'").lower())
            if mapped and mapped not in seen:
                seen.add(mapped)
                out.append(mapped)
        return out

    @property
    def resolved_jwt_issuer(self) -> str:
        if self.jwt_issuer:
            return self.jwt_issuer.rstrip("/")
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1"
        return ""

    def require_database(self) -> str:
        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is missing. Set a Postgres URI "
                "(postgresql+psycopg://...) or the local Compose URL. Sign-in is not required."
            )
        return self.database_url

    def missing_gemini(self) -> str | None:
        if not self.gemini_api_key:
            return (
                "GEMINI_API_KEY is not configured. Create a key at https://aistudio.google.com/ "
                "and set GEMINI_MODEL to a documented identifier such as gemini-3.8-flash."
            )
        return None

    def missing_youcam(self) -> str | None:
        if not self.youcam_api_key:
            return (
                "YOU_CAM_API_KEY is not configured. Request access from Perfect Corp / YouCam "
                "and set YOU_CAM_BASE_URL (default https://yce-api-01.makeupar.com), "
                "YOU_CAM_UNIT_COST, and YOU_CAM_ENABLED_CATEGORIES after live verification."
            )
        if self.youcam_unit_cost <= 0:
            return (
                "YOU_CAM_UNIT_COST must be a positive integer. Official AI Clothes VTO "
                "consumes documented units (currently 2 for V2/V3). Missing cost configuration "
                "blocks paid jobs."
            )
        if not self.youcam_category_list:
            return (
                "YOU_CAM_ENABLED_CATEGORIES is empty. Official categories are "
                "upper_body, lower_body, full_body, shoes, outer, auto. Enable only paths "
                "verified with consented live inputs. Lower-body product-only references "
                "are documented as unsupported."
            )
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
