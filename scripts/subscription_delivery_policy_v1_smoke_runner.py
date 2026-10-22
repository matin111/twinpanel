#!/usr/bin/env python3
from __future__ import annotations

import os
import runpy
from pathlib import Path

# The production database module configures a PostgreSQL QueuePool at import
# time. Use a non-routable PostgreSQL DSN so the engine can be constructed with
# the production pool contract without opening any external connection.
os.environ.setdefault("APP_SECRET_KEY", "subscription-delivery-policy-v1-smoke-secret")
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg2://twinpanel_smoke:twinpanel_smoke@127.0.0.1:1/"
    "twinpanel_smoke"
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
runpy.run_path(str(smoke_path), run_name="__main__")
