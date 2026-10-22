#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
from datetime import datetime

os.environ.setdefault("APP_SECRET_KEY", "subscription-delivery-policy-v1-smoke-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "subscription-delivery-policy-v1-node-secret")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Node,
    NodeProtocolConfig,
    NodeStatus,
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    SubscriptionStatus,
    Tunnel,
    TunnelStatus,
    User,
    UserRole,
)
from app.quota_models import QuotaDevice
from app.routers import account_delivery as ad
from app.routers import subscription_delivery_policy_v1 as api
from app.subscription_delivery_policy_v1 import (
    SubscriptionDeliveryPolicyState,
    SubscriptionNodeDeliveryMode,
    compile_explicit_stored_info,
    explicit_nodes,
    install_account_delivery_hooks,
    protocol_capabilities,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def items(payload: dict, protocol: str = "v2ray") -> list[dict]:
    for row in payload.get("credentials", []):
        if row.get("protocol") == protocol:
            value = row.get("items") or []
            return value if isinstance(value, list) else [value]
    return []


async def main() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        user = User(
            id=1,
            email="delivery-smoke@example.test",
            password_hash="x",
            full_name="Delivery Smoke",
            role=UserRole.USER,
            is_active=True,
        )
        iran = Node(
            id=1,
            name="iran-a",
            node_type=NodeType.IRAN,
            country_code="IR",
            public_ip="198.51.100.10",
            agent_url="ssh://iran-a",
            status=NodeStatus.ONLINE,
            show_to_users=True,
        )
        exit_a = Node(
            id=2,
            name="germany-a",
            node_type=NodeType.EXIT,
            country_code="DE",
            public_ip="203.0.113.20",
            agent_url="ssh://germany-a",
            status=NodeStatus.ONLINE,
            show_to_users=True,
            enable_v2ray=True,
            enable_l2tp=True,
        )
        exit_b = Node(
            id=3,
            name="usa-b",
            node_type=NodeType.EXIT,
            country_code="US",
            public_ip="203.0.113.30",
            agent_url="ssh://usa-b",
            status=NodeStatus.ONLINE,
            show_to_users=True,
            enable_v2ray=True,
            enable_l2tp=True,
        )
        tunnel_a = Tunnel(
            id=11,
            iran_node_id=1,
            exit_node_id=2,
            transport="wireguard",
            status=TunnelStatus.ONLINE,
            priority=10,
            is_active=True,
        )
        tunnel_b = Tunnel(
            id=12,
            iran_node_id=1,
            exit_node_id=3,
            transport="wireguard",
            status=TunnelStatus.ONLINE,
            priority=20,
            is_active=True,
        )
        sub = Subscription(
            id=100,
            user_id=1,
            plan_id=1,
            status=SubscriptionStatus.ACTIVE,
            traffic_limit_bytes=50 * 1024**3,
            traffic_used_bytes=1234,
            account_username="mv100",
            account_password_encrypted="secret-unchanged",
            share_code="stable-token-100",
        )
        legacy_sub = Subscription(
            id=101,
            user_id=1,
            plan_id=1,
            status=SubscriptionStatus.ACTIVE,
            traffic_limit_bytes=0,
            traffic_used_bytes=0,
            account_username="mv101",
            account_password_encrypted="legacy-secret",
            share_code="stable-token-101",
        )
        db.add_all([user, iran, exit_a, exit_b, tunnel_a, tunnel_b, sub, legacy_sub])
        db.add_all(
            [
                NodeProtocolConfig(id=1, node_id=2, protocol="v2ray", port=8443, transport="tcp", status="online"),
                NodeProtocolConfig(id=2, node_id=3, protocol="v2ray", port=8443, transport="tcp", status="online"),
                NodeProtocolConfig(id=3, node_id=2, protocol="l2tp", port=1701, transport="udp", status="online"),
                NodeProtocolConfig(id=4, node_id=3, protocol="l2tp", port=1701, transport="udp", status="online"),
            ]
        )
        explicit_membership = SubscriptionNode(id=201, subscription_id=100, node_id=2)
        legacy_membership_a = SubscriptionNode(id=202, subscription_id=101, node_id=2)
        legacy_membership_b = SubscriptionNode(id=203, subscription_id=101, node_id=3)
        db.add_all([explicit_membership, legacy_membership_a, legacy_membership_b])
        db.add(SubscriptionDeliveryPolicyState(subscription_id=100, mode="explicit"))
        mode = SubscriptionNodeDeliveryMode(
            subscription_node_id=201,
            direct_enabled=True,
            tunnel_enabled=True,
            tunnel_id=11,
            priority=10,
        )
        db.add(mode)
        db.add(SubscriptionProtocol(id=301, subscription_id=100, protocol="v2ray"))
        db.flush()

        original_item = {
            "node_id": 2,
            "node": "germany-a",
            "server": "old.invalid",
            "server_ip": "old.invalid",
            "port": 1,
            "uuid": "11111111-1111-4111-8111-111111111111",
            "uri": "vless://11111111-1111-4111-8111-111111111111@old.invalid:1?encryption=none&type=tcp#Germany",
        }
        db.add(
            ProtocolCredential(
                id=401,
                subscription_id=100,
                protocol="v2ray",
                config_text_encrypted=ad._enc([original_item]),
                is_active=True,
            )
        )
        db.add(
            QuotaDevice(
                id=501,
                subscription_id=100,
                protocol="v2ray",
                device_key="subscription:100:v2ray",
                credential_public_hash="pending-100-v2ray",
                status="active",
            )
        )
        db.commit()

        # Stable public token is an invariant of every policy mutation.
        ad._share_url = lambda _db, current: f"/v1/connect/{current.share_code}"

        # 1 Legacy subscriptions keep global legacy node behavior.
        install_account_delivery_hooks()
        legacy_ids = [node.id for node in ad._nodes(db, legacy_sub)]
        check(2 in legacy_ids and 3 in legacy_ids, "legacy node delivery changed")

        # 2/3/4 BOTH emits two profiles with the same cryptographic identity.
        both = compile_explicit_stored_info(ad, db, sub)
        both_items = items(both)
        check(len(both_items) == 2, "Both must emit tunnel + direct")
        check({row["delivery_mode"] for row in both_items} == {"tunnel", "direct"}, "Both modes missing")
        check({row["uuid"] for row in both_items} == {original_item["uuid"]}, "identity rotated across modes")
        check(both["subscription_link"].endswith("stable-token-100"), "share token changed")

        # 11 Tunnel offline + Tunnel-only => no hidden Direct fallback.
        mode.direct_enabled = False
        tunnel_a.status = TunnelStatus.OFFLINE
        db.commit()
        tunnel_only_down = compile_explicit_stored_info(ad, db, sub)
        check(items(tunnel_only_down) == [], "Tunnel-only silently fell back to Direct")

        # 12 Tunnel offline + Both => Direct remains independently usable.
        mode.direct_enabled = True
        db.commit()
        both_down = compile_explicit_stored_info(ad, db, sub)
        check([row["delivery_mode"] for row in items(both_down)] == ["direct"], "Both did not preserve Direct")

        # 3 Direct-only is independent of tunnel health.
        mode.tunnel_enabled = False
        db.commit()
        direct_only = compile_explicit_stored_info(ad, db, sub)
        check([row["delivery_mode"] for row in items(direct_only)] == ["direct"], "Direct-only depends on tunnel")

        # 13 Runtime protocol offline means Direct is not deliverable.
        cfg_a = db.query(NodeProtocolConfig).filter_by(node_id=2, protocol="v2ray").one()
        cfg_a.status = "offline"
        db.commit()
        check(items(compile_explicit_stored_info(ad, db, sub)) == [], "offline protocol leaked")
        cfg_a.status = "online"

        # 10 show_to_users=false is a hard customer-delivery gate.
        exit_a.show_to_users = False
        db.commit()
        check(items(compile_explicit_stored_info(ad, db, sub)) == [], "hidden node leaked")
        exit_a.show_to_users = True

        # 9 retired node never appears.
        exit_a.retired_at = datetime.utcnow()
        db.commit()
        check(items(compile_explicit_stored_info(ad, db, sub)) == [], "retired node leaked")
        exit_a.retired_at = None

        # 6 Protocol disabled removes it immediately without deleting credential.
        db.query(SubscriptionProtocol).filter_by(subscription_id=100, protocol="v2ray").delete()
        db.commit()
        check(items(compile_explicit_stored_info(ad, db, sub)) == [], "disabled protocol leaked")
        check(db.get(ProtocolCredential, 401) is not None, "credential history was deleted")
        db.add(SubscriptionProtocol(id=302, subscription_id=100, protocol="v2ray"))
        db.commit()

        # 5 Both route toggles off => target disappears, while bare membership is ignored.
        mode.direct_enabled = False
        mode.tunnel_enabled = False
        db.commit()
        check(items(compile_explicit_stored_info(ad, db, sub)) == [], "disabled target leaked")
        mode.direct_enabled = True

        # 19 A newly auto-synced bare SubscriptionNode does not leak into explicit policy.
        db.add(SubscriptionNode(id=204, subscription_id=100, node_id=3))
        db.commit()
        check([node.id for node in explicit_nodes(db, sub)] == [2], "bare autosync membership leaked")

        # 18 L2TP cannot select two Exit targets behind the same Iran ingress.
        bad_l2tp = api.DeliveryPolicyIn(
            protocols=["l2tp"],
            targets=[
                api.DeliveryTargetIn(node_id=2, enabled=True, tunnel_enabled=True, tunnel_id=11),
                api.DeliveryTargetIn(node_id=3, enabled=True, tunnel_enabled=True, tunnel_id=12),
            ],
        )
        try:
            api._validate_and_resolve(db, bad_l2tp)
        except HTTPException as exc:
            check(exc.status_code == 422, "L2TP exception returned wrong status")
        else:
            raise AssertionError("L2TP multi-exit primary exception was not enforced")

        # Modern protocols must not be advertised as production Account Delivery
        # until identity adapter + quota collector/enforcer are real.
        caps = {row["protocol"]: row for row in protocol_capabilities()}
        check(caps["hysteria2"]["account_delivery_ready"] is False, "modern capability overclaimed")
        check(caps["sudoku"]["revocation_scope"] == "delivery_only", "Sudoku revoke capability overclaimed")

        # 15/16/17 Reconcile reuses the existing identity and creates only a missing
        # node pair. Repeating it must create no duplicate user/peer/UUID.
        mode.direct_enabled = True
        mode.tunnel_enabled = False
        mode.tunnel_id = None
        membership_b = db.get(SubscriptionNode, 204)
        db.add(
            SubscriptionNodeDeliveryMode(
                subscription_node_id=membership_b.id,
                direct_enabled=True,
                tunnel_enabled=False,
                priority=20,
            )
        )
        db.commit()

        calls: list[tuple[int, str]] = []

        async def fake_xray(_db, node, _sub, _user, client_id):
            calls.append((int(node.id), str(client_id)))
            return {
                "node_id": int(node.id),
                "node": node.name,
                "server": node.public_ip,
                "server_ip": node.public_ip,
                "port": 8443,
                "uuid": str(client_id),
                "uri": f"vless://{client_id}@{node.public_ip}:8443?encryption=none&type=tcp#{node.name}",
            }

        ad._xray = fake_xray
        api.queue_subscription_enforcement = lambda *args, **kwargs: {"commands_created": 0}

        import app.services.quota_refresh as quota_refresh

        async def fake_quota_sync(_db, _subscription_id):
            return {"ok": True, "nodes": []}

        quota_refresh.sync_subscription_quota_nodes = fake_quota_sync

        first = await api._reconcile_explicit(db, sub)
        check(first["ok"], "first reconcile failed")
        check(calls == [(3, original_item["uuid"])], "missing node did not reuse V2Ray identity")
        second = await api._reconcile_explicit(db, sub)
        check(second["ok"], "second reconcile failed")
        check(len(calls) == 1, "idempotent reconcile created a duplicate identity")

        # 20 Quota/usage and stable token are untouched by policy/reconcile.
        db.refresh(sub)
        check(int(sub.traffic_used_bytes) == 1234, "usage history changed")
        check(sub.share_code == "stable-token-100", "subscription token changed")

    print("SUBSCRIPTION_DELIVERY_POLICY_V1_SMOKE_OK")


if __name__ == "__main__":
    asyncio.run(main())
