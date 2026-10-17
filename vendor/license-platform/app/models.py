from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TrialIdentity(Base):
    __tablename__ = "trial_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    trial_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trial_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaidLicense(Base):
    __tablename__ = "paid_licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    key_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True, nullable=False)
    edition: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)
    release_channel: Mapped[str] = mapped_column(String(24), default="stable", nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activation_fingerprint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    activation_reset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    customer_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    features: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Installation(Base):
    __tablename__ = "installations"
    __table_args__ = (
        UniqueConstraint("installation_id", name="uq_installation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    paid_license_id: Mapped[int | None] = mapped_column(ForeignKey("paid_licenses.id", ondelete="SET NULL"), nullable=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    paid_license: Mapped[PaidLicense | None] = relationship()


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("version", "channel", name="uq_release_version_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    package_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    minimum_updater_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    installable: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    notes_fa: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LicenseAuditEvent(Base):
    __tablename__ = "license_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    installation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    fingerprint_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    paid_license_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
