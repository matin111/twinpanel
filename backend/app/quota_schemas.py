from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ProtocolName = Literal["openconnect", "openvpn", "wireguard", "l2tp", "xray"]


class UsageEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=16, max_length=128)
    subscription_id: int = Field(gt=0)
    device_id: int = Field(gt=0)
    session_key: str | None = Field(default=None, max_length=160)
    protocol: ProtocolName
    source_key: str = Field(min_length=3, max_length=220)
    counter_mode: Literal["cumulative", "delta"]
    counter_epoch: str = Field(min_length=8, max_length=96)
    source_sequence: int = Field(ge=0, le=2**63 - 1)
    uplink_value: int = Field(ge=0, le=2**63 - 1)
    downlink_value: int = Field(ge=0, le=2**63 - 1)
    reported_at: datetime

    @field_validator("reported_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("reported_at must include timezone")
        return value


class SessionOpenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_key: str = Field(min_length=1, max_length=160)
    subscription_id: int = Field(gt=0)
    device_id: int = Field(gt=0)
    protocol: ProtocolName
    client_ip: str | None = Field(default=None, max_length=64)


class SessionCloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_key: str = Field(min_length=1, max_length=160)
    reason: str = Field(default="agent_disconnect", min_length=2, max_length=64)


class CommandAckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["succeeded", "failed", "rejected"]
    result_code: str = Field(min_length=2, max_length=64)
    result_message: str | None = Field(default=None, max_length=500)
