"""Additive durable status record for the node-install progress UI.

Contains no SSH password, node private keys, or subscription credentials.
The underlying legacy task still runs in-process, not in a durable executor.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class NodeInstallProgressV1(Base):
    __tablename__ = "node_install_progress_v1"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_name: Mapped[str] = mapped_column(String(120), nullable=False)
    node_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    stage: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    installed_protocols: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_protocols: Mapped[int | None] = mapped_column(Integer, nullable=True)
    users_assigned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
