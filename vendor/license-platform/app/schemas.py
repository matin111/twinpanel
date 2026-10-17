from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InstallationIdentityIn(BaseModel):
    installation_id: str = Field(min_length=8, max_length=64)
    machine_fingerprint: str = Field(min_length=32, max_length=128)
    product: str = "TwinPanel"
    version: str = Field(default="0.0.0", max_length=64)


class TrialIn(InstallationIdentityIn):
    pass


class ActivateIn(InstallationIdentityIn):
    license_key: str = Field(min_length=8, max_length=256)


class ValidateIn(InstallationIdentityIn):
    signed_entitlement: str | None = None


class ReleaseResolveIn(BaseModel):
    installation_id: str = Field(min_length=8, max_length=64)
    signed_entitlement: str = Field(min_length=40)
    current_version: str = Field(default="0.0.0", max_length=64)
    requested_version: str | None = Field(default=None, max_length=64)
    channel: str = Field(default="stable", max_length=24)


class InstallResolveIn(BaseModel):
    product: str = "TwinPanel"
    installation_id: str = Field(min_length=8, max_length=64)
    machine_fingerprint: str = Field(min_length=32, max_length=128)
    license_key: str | None = Field(default=None, max_length=256)
    requested_channel: str = Field(default="stable", max_length=24)
    updater_version: int = Field(default=1, ge=1, le=1000)


class AdminLicenseCreateIn(BaseModel):
    duration_days: int | None = Field(default=30, ge=1, le=3650)
    edition: str = Field(default="standard", max_length=32)
    release_channel: str = Field(default="stable", max_length=24)
    customer_ref: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)
    features: dict[str, Any] = Field(default_factory=dict)


class AdminLicenseExtendIn(BaseModel):
    days: int = Field(ge=1, le=3650)


class AdminReleaseRegisterIn(BaseModel):
    version: str = Field(min_length=3, max_length=64)
    channel: str = Field(default="stable", max_length=24)
    package_filename: str = Field(min_length=5, max_length=255)
    sha256: str = Field(min_length=64, max_length=64)
    minimum_updater_version: int = Field(default=1, ge=1, le=1000)
    installable: bool = False
    notes_fa: str | None = None
    notes_en: str | None = None


class AdminReleaseToggleIn(BaseModel):
    installable: bool


class AdminTrialResetIn(BaseModel):
    fingerprint_hash: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=3, max_length=500)
