#!/usr/bin/env python3
from __future__ import annotations

import os
import runpy
import tempfile
from pathlib import Path

# app imports subscription_plan_schema, whose import-time inspection opens a
# database connection. Use a disposable SQLite file: SQLAlchemy's file-backed
# SQLite QueuePool supports the production pool options, and inspection can
# connect without relying on an absent PostgreSQL server on port 1.
_smoke_db_directory = tempfile.TemporaryDirectory(prefix="twinpanel-policy-smoke-")
os.environ.setdefault("APP_SECRET_KEY", "subscription-delivery-policy-v1-smoke-secret")
os.environ["DATABASE_URL"] = (
    f"sqlite+pysqlite:///{Path(_smoke_db_directory.name) / 'bootstrap.sqlite3'}"
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault(
    "NODE_AGENT_SHARED_SECRET",
    "subscription-delivery-policy-v1-node-secret",
)

from app.database import Base
from app.models import (
    Node,
    NodeProtocolConfig,
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    Tunnel,
    User,
)
from app.quota_models import QuotaDevice
from app.subscription_delivery_policy_v1 import (
    SubscriptionDeliveryPolicyState,
    SubscriptionNodeDeliveryMode,
)

_real_create_all = Base.metadata.create_all


def _delivery_create_all(*, bind=None, **_kwargs) -> None:
    """Create only the dependency-closed schema used by this smoke.

    Importing Account Delivery also registers unrelated Store/Payment tables in
    the shared metadata. Creating every application table would make this smoke
    depend on unrelated model import order. The production schema remains
    untouched; only this in-memory SQLite test is scoped down.
    """

    _real_create_all(
        bind=bind,
        tables=[
            User.__table__,
            Plan.__table__,
            Node.__table__,
            Tunnel.__table__,
            Subscription.__table__,
            SubscriptionNode.__table__,
            SubscriptionProtocol.__table__,
            ProtocolCredential.__table__,
            NodeProtocolConfig.__table__,
            QuotaDevice.__table__,
            SubscriptionDeliveryPolicyState.__table__,
            SubscriptionNodeDeliveryMode.__table__,
        ],
    )


Base.metadata.create_all = _delivery_create_all

smoke_path = Path(__file__).with_name("subscription_delivery_policy_v1_smoke.py")
try:
    runpy.run_path(str(smoke_path), run_name="__main__")
finally:
    _smoke_db_directory.cleanup()
