from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from .database import SessionLocal
from .routers import modern_account_delivery_v1 as modern


# TWINPANEL_CLASSIC_NODE_PARALLEL_V1
#
# Account creation previously provisioned every Classic node serially. A plan
# with four selected nodes therefore paid the SSH/service latency four times for
# Cisco, WireGuard and V2Ray. These drivers mutate independent runtime files on
# different servers, so they can safely run per-node with bounded concurrency.
#
# OpenVPN intentionally remains on the canonical serial path because its client
# identity can be shared across nodes. L2TP also remains serial because it reads
# a central PSK lifecycle. Protocols themselves remain serial in
# modern_account_delivery_v1, so one server is never mutated by multiple Classic
# protocol drivers at the same time.


CLASSIC_NODE_CONCURRENCY_LIMIT = 3
PARALLEL_CLASSIC_PROTOCOLS = frozenset({"cisco", "wireguard", "v2ray"})

_ORIGINAL_CLASSIC = None
_INSTALLED = False


def _snapshot_subjects(sub: Any, user: Any):
    # Drivers only need these scalar attributes. Detached snapshots guarantee a
    # concurrent task can never lazy-load through the request SQLAlchemy Session.
    return (
        SimpleNamespace(
            id=int(sub.id),
            account_username=str(getattr(sub, "account_username", "") or ""),
        ),
        SimpleNamespace(id=int(user.id)),
    )


async def _parallel_classic_protocol(
    ad: Any,
    db,
    sub,
    user,
    protocol: str,
    nodes: list,
    username: str,
    password: str,
    xray_id: str,
):
    assert _ORIGINAL_CLASSIC is not None

    protocol = str(protocol or "").strip().lower()
    if protocol not in PARALLEL_CLASSIC_PROTOCOLS or len(nodes) < 2:
        return await _ORIGINAL_CLASSIC(
            ad,
            db,
            sub,
            user,
            protocol,
            nodes,
            username,
            password,
            xray_id,
        )

    flag = modern.CLASSIC_NODE_FLAGS[protocol]
    node_timeout = max(
        1.0,
        float(
            modern.PROTOCOL_PROVISION_TIMEOUT_SECONDS.get(
                protocol,
                modern.DEFAULT_PROTOCOL_PROVISION_TIMEOUT_SECONDS,
            )
        ),
    )
    sub_snapshot, user_snapshot = _snapshot_subjects(sub, user)
    semaphore = asyncio.Semaphore(CLASSIC_NODE_CONCURRENCY_LIMIT)

    outcomes: list[tuple[int, dict[str, Any] | None, dict[str, str] | None]] = []
    tasks = []

    async def run_node(index: int, node_id: int, node_name: str):
        async with semaphore:
            task_db = SessionLocal()
            try:
                task_node = task_db.get(modern.Node, int(node_id))
                if task_node is None:
                    return (
                        index,
                        None,
                        {
                            "protocol": protocol,
                            "node": node_name,
                            "error": "Server disappeared during provisioning",
                        },
                    )

                async def provision_node():
                    if protocol == "cisco":
                        return await ad._cisco(
                            task_db,
                            task_node,
                            sub_snapshot,
                            user_snapshot,
                            username,
                            password,
                        )
                    if protocol == "wireguard":
                        return await ad._wireguard(
                            task_db,
                            task_node,
                            sub_snapshot,
                            user_snapshot,
                        )
                    return await ad._xray(
                        task_db,
                        task_node,
                        sub_snapshot,
                        user_snapshot,
                        xray_id,
                    )

                try:
                    item = await modern.await_hard_timeout(
                        provision_node(),
                        timeout_seconds=node_timeout,
                        wait_for_cancel=True,
                    )
                    return index, item, None
                except asyncio.TimeoutError:
                    return (
                        index,
                        None,
                        {
                            "protocol": protocol,
                            "node": node_name,
                            "error": (
                                "Provisioning timeout on this server after "
                                f"{int(node_timeout)} seconds"
                            ),
                        },
                    )
                except Exception as exc:
                    return (
                        index,
                        None,
                        {
                            "protocol": protocol,
                            "node": node_name,
                            "error": str(exc)[:800],
                        },
                    )
            finally:
                task_db.close()

    for index, node in enumerate(nodes):
        node_name = str(getattr(node, "name", "") or f"node-{getattr(node, 'id', index)}")
        if not bool(getattr(node, flag, False)):
            outcomes.append(
                (
                    index,
                    None,
                    {
                        "protocol": protocol,
                        "node": node_name,
                        "error": "Protocol is not enabled on this server",
                    },
                )
            )
            continue

        tasks.append(
            asyncio.create_task(
                run_node(index, int(node.id), node_name)
            )
        )

    if tasks:
        outcomes.extend(await asyncio.gather(*tasks))

    outcomes.sort(key=lambda value: value[0])
    items = [item for _, item, _ in outcomes if item is not None]
    errors = [error for _, _, error in outcomes if error is not None]

    if items:
        cred = modern._get_credential(db, int(sub.id), protocol)
        cred.username = username if protocol == "cisco" else None
        cred.secret_encrypted = (
            ad._enc({"password": password})
            if protocol == "cisco"
            else None
        )
        cred.config_text_encrypted = ad._enc(items)
        cred.is_active = True

    return items, errors


def install() -> None:
    global _ORIGINAL_CLASSIC, _INSTALLED

    if _INSTALLED:
        return

    current = modern._provision_classic_protocol
    if getattr(current, "_twinpanel_classic_node_parallel_v1", False):
        _INSTALLED = True
        return

    _ORIGINAL_CLASSIC = current
    _parallel_classic_protocol._twinpanel_classic_node_parallel_v1 = True
    modern._provision_classic_protocol = _parallel_classic_protocol
    _INSTALLED = True
