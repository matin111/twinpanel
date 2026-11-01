from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import asyncssh
from sqlalchemy.orm import Session

from .models import Node, NodeAccess, Subscription
from .services.hard_async_timeout import await_hard_timeout
from .routers import modern_account_delivery_v1 as modern


# TWINPANEL_MODERN_NODE_PARALLEL_V1
#
# Only node-level SSH work for ONE modern protocol is parallelized. Protocols
# themselves remain sequential, so two different protocol runtimes on the same
# server are never mutated at the same time. Classic protocols, quota,
# accounting and fulfillment are untouched.
MAX_PARALLEL_MODERN_NODES = 3
_INSTALLED = False


def _access_snapshot(db: Session, node: Node) -> dict[str, Any]:
    """Read SSH metadata before spawning tasks; tasks never touch the ORM session."""
    access = (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(node.id))
        .first()
    )
    if access is None:
        raise RuntimeError(
            "دسترسی امن این سرور ثبت نشده است. یک‌بار «ثبت دسترسی سرور» را انجام دهید."
        )

    key_path = Path(str(access.private_key_path or ""))
    if not key_path.exists():
        raise RuntimeError(
            "کلید دسترسی این سرور پیدا نشد. دسترسی را دوباره ثبت کنید."
        )

    return {
        "host": str(node.public_ip),
        "port": int(access.ssh_port),
        "username": str(access.ssh_username),
        "key_path": str(key_path),
    }


async def _connect_snapshot(snapshot: dict[str, Any]):
    try:
        return await asyncssh.connect(
            snapshot["host"],
            port=int(snapshot["port"]),
            username=str(snapshot["username"]),
            client_keys=[str(snapshot["key_path"])],
            known_hosts=None,
            connect_timeout=12,
            login_timeout=12,
        )
    except Exception as exc:
        raise RuntimeError(f"اتصال ذخیره‌شده SSH ناموفق بود: {exc}") from exc


def _node_error(protocol: str, node: Node, message: str) -> dict[str, str]:
    return {
        "protocol": str(protocol),
        "node": str(node.name),
        "error": str(message)[:800],
    }


async def _generate_standalone_secret(
    target: dict[str, Any],
    *,
    protocol: str,
    subscription_id: int,
    new_account_secret,
):
    conn = None
    try:
        conn = await _connect_snapshot(target["access"])
        return await new_account_secret(conn, protocol, int(subscription_id))
    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()


async def _provision_modern_protocol_parallel(
    ad: Any,
    db: Session,
    sub: Subscription,
    protocol: str,
    nodes: list[Node],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Preserve modern provisioning semantics while overlapping different nodes.

    DB/config/access reads happen synchronously before asyncio tasks start. The
    concurrent section performs remote SSH work only, so SQLAlchemy Session is
    never used by more than one task.
    """
    cred = modern._get_credential(db, sub.id, protocol)
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    previous_secret = None
    if protocol in modern.SINGBOX_ACCOUNT_PROTOCOLS:
        from .singbox_subscription_accounts import apply_account, secret_to_dict

        previous_secret = modern._stored_singbox_secret(ad, cred, protocol)
        secret = modern._singbox_secret(ad, cred, protocol, sub)
        standalone = False
        new_account_secret = None
    else:
        from .standalone_subscription_accounts import (
            apply_account,
            new_account_secret,
            secret_to_dict,
        )

        secret = modern._stored_standalone_secret(ad, cred, protocol)
        standalone = True

    targets: list[dict[str, Any]] = []
    for node in nodes:
        cfg = modern._modern_runtime_config(db, node, protocol)
        if cfg is None or modern._status_value(cfg.status) != "online":
            errors.append(
                _node_error(protocol, node, "Protocol runtime is not online on this server")
            )
            continue

        try:
            access = _access_snapshot(db, node)
        except Exception as exc:
            errors.append(_node_error(protocol, node, str(exc)))
            continue

        port = int(cfg.port or 0)
        if standalone and not 1 <= port <= 65535:
            errors.append(_node_error(protocol, node, f"{protocol} runtime port is unavailable"))
            continue

        _ = (
            node.id,
            node.name,
            node.public_ip,
            getattr(node, "public_domain", None),
            getattr(node, "country_code", None),
        )
        targets.append({"node": node, "port": port, "access": access})

    if not targets:
        return items, errors

    if standalone and secret is None:
        assert new_account_secret is not None
        remaining: list[dict[str, Any]] = []
        generated = False
        for index, target in enumerate(targets):
            node = target["node"]
            try:
                secret = await await_hard_timeout(
                    _generate_standalone_secret(
                        target,
                        protocol=protocol,
                        subscription_id=int(sub.id),
                        new_account_secret=new_account_secret,
                    ),
                    timeout_seconds=modern.MODERN_NODE_PROVISION_TIMEOUT_SECONDS,
                    wait_for_cancel=True,
                )
                remaining = targets[index:]
                generated = True
                break
            except asyncio.TimeoutError:
                errors.append(
                    _node_error(
                        protocol,
                        node,
                        "Secret generation timeout on this server after "
                        f"{int(modern.MODERN_NODE_PROVISION_TIMEOUT_SECONDS)} seconds",
                    )
                )
            except Exception as exc:
                errors.append(_node_error(protocol, node, str(exc)))

        if not generated or secret is None:
            return items, errors
        targets = remaining

    semaphore = asyncio.Semaphore(MAX_PARALLEL_MODERN_NODES)

    async def provision_target(target: dict[str, Any]):
        node = target["node"]

        async def remote_work() -> dict[str, Any]:
            conn = None
            try:
                conn = await _connect_snapshot(target["access"])
                if standalone:
                    item = await apply_account(conn, node, secret, int(target["port"]))
                    if protocol == "amneziawg":
                        from .amneziawg_egress_v221 import ensure_amneziawg_egress

                        egress = await ensure_amneziawg_egress(conn)
                        item["egress_contract"] = int(egress["contract"])
                    return item

                previous_username = str(
                    getattr(previous_secret, "username", "") or ""
                ).strip()
                current_username = str(getattr(secret, "username", "") or "").strip()
                if (
                    protocol in modern.SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS
                    and previous_username
                    and previous_username != current_username
                ):
                    await modern._remove_singbox_identity(
                        conn,
                        protocol,
                        previous_username,
                    )

                item = await apply_account(conn, node, secret)
                if protocol in modern.SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS:
                    item = modern._bind_unique_client_tags(
                        item,
                        node=node,
                        protocol=protocol,
                        username=current_username,
                    )
                return item
            finally:
                if conn is not None:
                    conn.close()
                    await conn.wait_closed()

        async with semaphore:
            try:
                item = await await_hard_timeout(
                    remote_work(),
                    timeout_seconds=modern.MODERN_NODE_PROVISION_TIMEOUT_SECONDS,
                    wait_for_cancel=True,
                )
                return item, None
            except asyncio.TimeoutError:
                return None, _node_error(
                    protocol,
                    node,
                    "Provisioning timeout on this server after "
                    f"{int(modern.MODERN_NODE_PROVISION_TIMEOUT_SECONDS)} seconds",
                )
            except Exception as exc:
                return None, _node_error(protocol, node, str(exc))

    outcomes = await asyncio.gather(*(provision_target(target) for target in targets))
    for item, error in outcomes:
        if item is not None:
            items.append(item)
        if error is not None:
            errors.append(error)

    if items and secret is not None:
        cred.username = modern._credential_identity(protocol, secret)
        cred.secret_encrypted = ad._enc(secret_to_dict(secret))
        cred.config_text_encrypted = ad._enc(items)
        cred.is_active = True

    return items, errors


def install_bounded_modern_node_provisioning_v1() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    current = modern._provision_modern_protocol
    if getattr(current, "_twinpanel_bounded_modern_node_v1", False):
        _INSTALLED = True
        return

    _provision_modern_protocol_parallel._twinpanel_bounded_modern_node_v1 = True
    modern._provision_modern_protocol = _provision_modern_protocol_parallel
    _INSTALLED = True
