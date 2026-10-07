from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import (
    Node,
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
)
from .quota_models import (
    QuotaDevice,
    QuotaNodeCommand,
    QuotaSession,
)


# Protocol name used by panel/database
# -> protocol name used by quota agent.
AGENT_PROTOCOL = {
    "cisco": "openconnect",
    "openconnect": "openconnect",
    "openvpn": "openvpn",
    "wireguard": "wireguard",
    "l2tp": "l2tp",
    "v2ray": "xray",
    "xray": "xray",
}


SESSION_ALIASES = {
    "openconnect": {
        "openconnect",
        "cisco",
    },
    "openvpn": {
        "openvpn",
    },
    "wireguard": {
        "wireguard",
    },
    "l2tp": {
        "l2tp",
    },
    "xray": {
        "xray",
        "v2ray",
    },
}


def _selected_protocols(
    db: Session,
    subscription_id: int,
) -> list[str]:
    return [
        str(row[0]).lower()
        for row in (
            db.query(
                SubscriptionProtocol.protocol
            )
            .filter(
                SubscriptionProtocol.subscription_id
                == subscription_id
            )
            .order_by(
                SubscriptionProtocol.id
            )
            .all()
        )
    ]


def _provisioned_protocols(
    db: Session,
    subscription_id: int,
) -> set[str]:
    return {
        str(row[0]).lower()
        for row in (
            db.query(
                ProtocolCredential.protocol
            )
            .filter(
                ProtocolCredential.subscription_id
                == subscription_id,
                ProtocolCredential.is_active.is_(
                    True
                ),
            )
            .all()
        )
    }


def _exit_nodes(
    db: Session,
    subscription_id: int,
) -> list[Node]:
    return (
        db.query(Node).filter(Node.retired_at.is_(None))
        .join(
            SubscriptionNode,
            SubscriptionNode.node_id
            == Node.id,
        )
        .filter(
            SubscriptionNode.subscription_id
            == subscription_id,
            Node.node_type == NodeType.EXIT,
        )
        .order_by(Node.id)
        .all()
    )


def _active_session_keys(
    db: Session,
    subscription_id: int,
    node_id: int,
    protocol: str,
) -> list[str]:
    aliases = SESSION_ALIASES.get(
        protocol,
        {protocol},
    )

    rows = (
        db.query(
            QuotaSession.session_key
        )
        .filter(
            QuotaSession.subscription_id
            == subscription_id,
            QuotaSession.node_id
            == node_id,
            QuotaSession.status
            == "active",
            QuotaSession.protocol.in_(
                aliases
            ),
        )
        .all()
    )

    return [
        str(row[0])
        for row in rows
        if row[0]
    ]



# TWINPANEL_QUOTA_DEVICE_LIFECYCLE_V1
def _quota_protocol_names(values) -> set[str]:
    names: set[str] = set()

    for value in values:
        raw = str(value or "").strip().lower()

        if not raw:
            continue

        agent = AGENT_PROTOCOL.get(raw, raw)

        names.add(raw)
        names.add(agent)
        names.update(
            SESSION_ALIASES.get(
                agent,
                {agent},
            )
        )

    return names


def _sync_quota_devices(
    db: Session,
    subscription_id: int,
    *,
    command_type: str,
    protocols: list[str] | None,
    targets: list[tuple[str, str]],
    node_ids: list[int] | None,
    now: datetime,
) -> int:
    # Node-scoped revoke/restore is an Exit migration.
    # It must never globally disable the device.
    if node_ids is not None:
        return 0

    query = (
        db.query(QuotaDevice)
        .filter(
            QuotaDevice.subscription_id
            == subscription_id
        )
    )

    if command_type == "revoke_subscription":
        # Full suspend/delete/quota exhaustion:
        # revoke every device, even if credential
        # selection is already inconsistent.
        if protocols is not None:
            names = _quota_protocol_names(
                protocols
            )

            if not names:
                return 0

            query = query.filter(
                QuotaDevice.protocol.in_(names)
            )

        new_status = "revoked"

    else:
        # Restore ONLY currently valid/provisioned
        # protocols resolved by enforcement.
        names = _quota_protocol_names(
            [
                value
                for pair in targets
                for value in pair
            ]
        )

        if not names:
            return 0

        query = query.filter(
            QuotaDevice.protocol.in_(names)
        )

        new_status = "active"

    rows = query.with_for_update().all()
    changed = 0

    for device in rows:
        if new_status == "revoked":
            if device.status != "revoked":
                device.status = "revoked"
                device.revoked_at = now
                changed += 1

        else:
            if (
                device.status != "active"
                or device.revoked_at is not None
            ):
                device.status = "active"
                device.revoked_at = None
                changed += 1

    return changed

def queue_subscription_enforcement(
    db: Session,
    subscription: Subscription,
    *,
    command_type: str,
    reason: str,
    protocols: list[str] | None = None,
    node_ids: list[int] | None = None,
) -> dict:
    if command_type not in {
        "revoke_subscription",
        "restore_subscription",
    }:
        raise ValueError(
            "invalid enforcement command type"
        )

    selected = _selected_protocols(
        db,
        subscription.id,
    )

    provisioned = _provisioned_protocols(
        db,
        subscription.id,
    )

    canonical_order = [
        "cisco",
        "openconnect",
        "openvpn",
        "wireguard",
        "l2tp",
        "v2ray",
        "xray",
    ]

    def resolve_provisioned(
        value: str,
    ) -> str | None:
        value = str(
            value or ""
        ).strip().lower()

        if value in provisioned:
            return value

        normalized = AGENT_PROTOCOL.get(
            value,
            value,
        )

        for candidate in provisioned:
            if (
                AGENT_PROTOCOL.get(
                    candidate,
                    candidate,
                )
                == normalized
            ):
                return candidate

        return None

    if protocols is None:
        if (
            command_type
            == "revoke_subscription"
        ):
            # Revoke ALL live credentials,
            # even if an old panel selection row
            # has already become inconsistent.
            raw_candidates = [
                p
                for p in canonical_order
                if p in provisioned
            ]

            raw_candidates += sorted(
                provisioned
                - set(raw_candidates)
            )

        else:
            # Restore only protocols which are
            # still selected in the panel.
            raw_candidates = [
                p
                for p in selected
                if resolve_provisioned(p)
            ]

    else:
        raw_candidates = []

        for supplied in protocols:
            resolved = resolve_provisioned(
                supplied
            )

            if not resolved:
                continue

            if (
                command_type
                == "restore_subscription"
                and resolved not in selected
                and supplied not in selected
            ):
                continue

            if resolved not in raw_candidates:
                raw_candidates.append(
                    resolved
                )

    targets: list[
        tuple[str, str]
    ] = []

    seen = set()

    for raw in raw_candidates:
        normalized = AGENT_PROTOCOL.get(
            raw
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)

        targets.append(
            (
                raw,
                normalized,
            )
        )

    if node_ids is None:
        nodes = _exit_nodes(
            db,
            subscription.id,
        )

    else:
        wanted = list(
            dict.fromkeys(
                int(x)
                for x in node_ids
                if int(x) > 0
            )
        )

        rows = (
            db.query(Node).filter(Node.retired_at.is_(None))
            .filter(
                Node.id.in_(wanted),
                Node.node_type
                == NodeType.EXIT,
            )
            .all()
            if wanted
            else []
        )

        by_id = {
            int(node.id): node
            for node in rows
        }

        nodes = [
            by_id[node_id]
            for node_id in wanted
            if node_id in by_id
        ]

    if targets and not nodes:
        raise RuntimeError(
            "اشتراک دارای اطلاعات اتصال است "
            "ولی سرور خروجی ندارد"
        )

    operation_id = uuid.uuid4().hex
    now = datetime.utcnow()

    devices_updated = _sync_quota_devices(
        db,
        subscription.id,
        command_type=command_type,
        protocols=protocols,
        targets=targets,
        node_ids=node_ids,
        now=now,
    )

    commands = []

    for node in nodes:
        for (
            source_protocol,
            agent_protocol,
        ) in targets:

            session_keys = (
                _active_session_keys(
                    db,
                    subscription.id,
                    node.id,
                    agent_protocol,
                )
            )

            command_id = (
                uuid.uuid4().hex
            )

            idempotency_key = (
                "subscription-enforcement:"
                f"{subscription.id}:"
                f"{operation_id}:"
                f"{node.id}:"
                f"{agent_protocol}:"
                f"{command_type}"
            )

            db.add(
                QuotaNodeCommand(
                    command_id=
                        command_id,
                    node_id=
                        node.id,
                    command_type=
                        command_type,
                    payload={
                        "subscription_id":
                            subscription.id,
                        "protocol":
                            agent_protocol,
                        "reason":
                            reason,
                        "session_keys":
                            session_keys,
                    },
                    nonce=
                        secrets.token_urlsafe(
                            24
                        ),
                    idempotency_key=
                        idempotency_key,
                    status="pending",
                    issued_at=now,
                    expires_at=(
                        now
                        + timedelta(hours=24)
                    ),
                )
            )

            commands.append({
                "command_id":
                    command_id,
                "node_id":
                    node.id,
                "protocol":
                    agent_protocol,
                "source_protocol":
                    source_protocol,
                "session_count":
                    len(session_keys),
            })

    return {
        "operation_id":
            operation_id,
        "commands":
            commands,
        "commands_created":
            len(commands),
        "devices_updated":
            devices_updated,
    }

