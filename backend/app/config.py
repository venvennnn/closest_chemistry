from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    youcam_api_key: str = ""
    youcam_base_url: str = "https://yce-api-01.makeupar.com"
    youcam_engine_version: str = "cloth-v4"
    youcam_unit_cost: int = 2
    youcam_enabled_categories: str = ""
    youcam_poll_interval_seconds: int = 10
    youcam_poll_timeout_seconds: int = 180
    youcam_webhook_secret: str = ""

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
        return [
            item.strip()
            for item in self.youcam_enabled_categories.split(",")
            if item.strip() in YOU_CAM_CATEGORIES
        ]

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
