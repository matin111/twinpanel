from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class MigrationImportRecord(Base):
    __tablename__ = "migration_import_records"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_migration_source_identity"),
        UniqueConstraint("legacy_token", name="uq_migration_legacy_token"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    legacy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_token: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    preserved_payload_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="imported", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
