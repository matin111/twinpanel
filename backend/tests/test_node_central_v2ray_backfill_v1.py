"""Central membership + V2Ray safe node provisioning regression tests.

Synthetic in-memory SQLite only. No SSH calls, no service restarts.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType,
    ProtocolCredential, Subscription, SubscriptionNode,
    SubscriptionProtocol, SubscriptionStatus, User,
)
from app.routers import account_delivery as ad
from app.services.central_node_entitlements_v1 import (
    account_is_eligible, eligible_node_subscriptions, protocol_live_on_exit,
)
from app import xray_profile_reconcile_v36 as reconcile
from scripts import twinpanel_existing_node_xray_backfill_v1 as xray_backfill


@pytest.fixture
def db():
    engine=create_engine(
        "sqlite://", connect_args={"check_same_thread":False},poolclass=StaticPool
    )
    for table in (
        User.__table__, Node.__table__, Subscription.__table__,
        SubscriptionNode.__table__, SubscriptionProtocol.__table__,
        NodeProtocolConfig.__table__, ProtocolCredential.__table__,
    ):
        table.create(engine)
    with Session(engine) as session:
        session.add(User(
            id=1,email="test-node-provision@example.test",
            password_hash="not-a-real-password",
        ))
        session.add(Node(
            id=13,name="Germany Test",public_ip="192.0.2.13",
            agent_url="https://192.0.2.13:9443",
            node_type=NodeType.EXIT,country_code="DE",
            status=NodeStatus.ONLINE,show_to_users=True,
            enable_v2ray=True,
        ))
        session.add(NodeProtocolConfig(
            id=31,node_id=13,protocol="v2ray",status="online",port=443,
        ))
        now=datetime.utcnow()
        for sid,status,expires,used,limit,selected,member in (
            (1,SubscriptionStatus.ACTIVE,None,0,100,True,True),
            (2,SubscriptionStatus.ACTIVE,None,0,100,True,False),
            (3,SubscriptionStatus.ACTIVE,now-timedelta(days=1),0,100,True,True),
            (4,SubscriptionStatus.ACTIVE,None,100,100,True,True),
            (5,SubscriptionStatus.SUSPENDED,None,0,100,True,True),
            (6,SubscriptionStatus.ACTIVE,None,0,100,False,True),
            (7,SubscriptionStatus.ACTIVE,None,0,100,True,True),
        ):
            session.add(Subscription(
                id=sid,user_id=1,plan_id=1,status=status,
                created_at=now if sid==7 else now-timedelta(days=10),
                expires_at=expires,traffic_used_bytes=used,
                traffic_limit_bytes=limit,
            ))
            if member:
                session.add(SubscriptionNode(
                    id=100+sid,subscription_id=sid,node_id=13,
                ))
            if selected:
                session.add(SubscriptionProtocol(
                    id=200+sid,subscription_id=sid,protocol="v2ray",
                ))
        session.commit()
        yield session
    engine.dispose()


def test_entitlement_requires_membership_plan_active_expiry_and_quota(db):
    assert protocol_live_on_exit(db,13,"v2ray")
    ids=[s.id for s in eligible_node_subscriptions(db,13,"v2ray",imported_only=False)]
    assert ids==[1,7]
    for sid in (2,3,4,5,6):
        assert not account_is_eligible(db,13,sid,"v2ray")
    assert account_is_eligible(db,13,1,"v2ray")
    assert not protocol_live_on_exit(db,13,"grpc")


def test_pending_xray_filters_active_old_missing_accounts(db):
    items=xray_backfill.pending_for_node(db,13)
    assert items==[1]
    assert xray_backfill.pending_for_node(db,13,subscription_id=7)==[]
    assert xray_backfill.pending_for_node(db,13,subscription_id=2)==[]
    assert xray_backfill.pending_for_node(db,13,subscription_id=1)==[1]


def test_v2ray_node_preserves_previous_uuid_and_delivery_items(db):
    previous_uuid=str(uuid.uuid4())
    preserved={
        "node_id":7,"uuid":previous_uuid,"uri":"vless://"+previous_uuid+"@192.0.2.7:443",
        "profiles":[{"id":"ws","uri":"some-previous-uri"}],
    }
    other_credential=ProtocolCredential(
        id=801,subscription_id=1,protocol="v2ray",
        is_active=True,config_text_encrypted=ad._enc([preserved]),
    )
    db.add(other_credential)
    db.commit()

    async def fake_remote(database,node,sub,user,client_id):
        assert client_id==previous_uuid
        assert node.id==13 and sub.id==1
        return {
            "node_id":13,"uuid":client_id,
            "profiles":[{"id":"ws","uri":"vless://safe-new-profile"}],
        }
    with patch.object(
        reconcile.xray_modern_runtime,"_xray_account_modern",
        side_effect=fake_remote,
    ) as remote:
        done=asyncio.run(
            reconcile._reconcile_subscription_for_exit(db,db.get(Subscription,1),db.get(Node,13))
        )
    assert done["ok"] and not done["skipped"]
    remote.assert_called_once()
    old,new=ad._dec(db.get(ProtocolCredential,801).config_text_encrypted)
    assert old==preserved
    assert new["node_id"]==13 and new["uuid"]==previous_uuid
    assert db.get(ProtocolCredential,801).is_active


def test_no_remote_call_for_unentitled_or_expired_sub(db):
    with patch.object(
        reconcile.xray_modern_runtime,"_xray_account_modern",
        new_callable=AsyncMock,
    ) as remote:
        for sid in (2,3,4,5,6):
            result=asyncio.run(reconcile._reconcile_subscription_for_exit(
                db,db.get(Subscription,sid),db.get(Node,13),
            ))
            assert result.get("skipped")
        remote.assert_not_called()


def test_legacy_cli_exposes_v2ray_but_never_unbounded_batch():
    from scripts.twinpanel_existing_node_backfill_v1 import parse_args
    options=parse_args(["--node-id","13","--protocol","v2ray"])
    assert options.apply is False
    assert options.protocol=="v2ray"
    with pytest.raises(SystemExit):
        parse_args(["--node-id","13","--protocol","v2ray","--apply"])
    assert xray_backfill.CANARY_MATURITY_MINUTES>=10
