"""Durable, scoped auto-backfill queue for published Exit nodes.

Only node membership publication enqueues these rows. The independent systemd
worker owns SSH execution. Xray/V2Ray is intentionally not part of this queue.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class NodeBackfillJobV1(Base):
    __tablename__ = "node_backfill_jobs_v1"

    node_id = Column(Integer, ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)
    protocol = Column(String(24), primary_key=True)
    state = Column(String(24), nullable=False, default="queued", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    completed_pairs = Column(Integer, nullable=False, default=0)
    last_batch = Column(Integer, nullable=False, default=0)
    run_after = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    lease_until = Column(DateTime, nullable=True)
    lease_token = Column(String(64), nullable=True)
    error_code = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
