from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TPLIC_",
        env_file=None,
        extra="ignore",
    )

    app_name: str = "TwinPanel License Platform"
    app_env: str = "production"

    database_url: str
    admin_token: str = Field(min_length=32)
    license_key_pepper: str = Field(min_length=32)

    signing_private_key_file: Path = Path("/etc/twinpanel-license/private.pem")
    signing_public_key_file: Path = Path("/etc/twinpanel-license/public.pem")

    public_base_url: str
    release_root: Path = Path("/var/lib/twinpanel-license/releases")

    trial_days: int = Field(default=7, ge=1, le=30)
    entitlement_ttl_seconds: int = Field(default=172800, ge=3600, le=604800)
    download_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)

    default_release_channel: str = "stable"
    issuer: str = "twinpanel-license"
    audience: str = "twinpanel"


settings = Settings()
