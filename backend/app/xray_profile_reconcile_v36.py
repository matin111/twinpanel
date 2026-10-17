from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import (
    Node,
    NodeProtocolConfig,
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionProtocol,
    User,
)
from .routers import account_delivery
from . import xray_modern_runtime


# Restored from the previously merged V36 production runtime. Existing UUIDs
# are reused; reconciliation only fills profiles the current Exit can expose.
_runtime_applied = False
_original_ensure_subscription_modern = None

_jobs: dict[str, dict[str, Any]] = {}
_running_by_exit: dict[int, str] = {}
_job_lock = asyncio.Lock()
_JOB_TTL_SECONDS = 3600.0


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _profile_ids(item: dict[str, Any] | None) -> set[str]:
    if not isinstance(item, dict):
        return set()
    profiles = item.get("profiles")
    if not isinstance(profiles, list):
        return set()
    return {
        str(profile.get("id") or "").strip().lower()
        for profile in profiles
        if isinstance(profile, dict)
    }


def _effective_domain(node: Node) -> str:
    return str(
        getattr(node, "xray_domain", None)
        or getattr(node, "public_domain", None)
        or ""
    ).strip().lower()


def _required_profiles(node: Node) -> set[str]:
    required = {
        xray_modern_runtime.PROFILE_XHTTP,
        xray_modern_runtime.PROFILE_GRPC,
    }
    if _effective_domain(node):
        required.update(
            {
                xray_modern_runtime.PROFILE_WS,
                xray_modern_runtime.PROFILE_HTTPUPGRADE,
            }
        )
    return required


def _item_complete_for_node(
    item: dict[str, Any] | None,
    node: Node,
) -> bool:
    return _required_profiles(node) <= _profile_ids(item)


def _eligible_nodes(db: Session) -> list[Node]:
    rows: list[Node] = []
    for node in (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
        )
        .order_by(Node.id.asc())
        .all()
    ):
        if not bool(getattr(node, "enable_v2ray", False)):
            continue
        cfg = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == int(node.id),
                NodeProtocolConfig.protocol == "v2ray",
            )
            .first()
        )
        if not cfg or _enum_value(cfg.status) != "online":
            continue
        rows.append(node)
    return rows


def _stored_items(
    db: Session,
    subscription_id: int,
) -> tuple[ProtocolCredential | None, list[dict[str, Any]]]:
    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == int(subscription_id),
            ProtocolCredential.protocol == "v2ray",
        )
        .first()
    )
    raw = (
        account_delivery._dec(cred.config_text_encrypted)
        if cred and cred.config_text_encrypted
        else None
    )
    if isinstance(raw, list):
        items = [dict(item) for item in raw if isinstance(item, dict)]
    elif isinstance(raw, dict):
        items = [dict(raw)]
    else:
        items = []
    return cred, items


def _items_by_node(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    for item in items:
        try:
            node_id = int(item.get("node_id"))
        except (TypeError, ValueError):
            continue
        output[node_id] = item
    return output


async def _ensure_subscription_modern_v36(
    db: Session,
    sub: Subscription,
    *,
    force: bool = False,
):
    assert _original_ensure_subscription_modern is not None
    if force:
        return await _original_ensure_subscription_modern(db, sub, force=True)

    selected = {
        str(row[0] or "").strip().lower()
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == int(sub.id))
            .all()
        )
    }
    if "v2ray" not in selected:
        return await _original_ensure_subscription_modern(db, sub, force=False)

    _cred, items = _stored_items(db, int(sub.id))
    by_node = _items_by_node(items)
    needs_refresh = any(
        not _item_complete_for_node(by_node.get(int(node.id)), node)
        for node in _eligible_nodes(db)
    )
    return await _original_ensure_subscription_modern(
        db,
        sub,
        force=bool(needs_refresh),
    )


async def _reconcile_subscription_for_exit(
    db: Session,
    sub: Subscription,
    exit_node: Node,
) -> dict[str, Any]:
    selected = {
        str(row[0] or "").strip().lower()
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == int(sub.id))
            .all()
        )
    }
    if "v2ray" not in selected:
        return {"ok": True, "skipped": True, "reason": "v2ray_not_selected"}

    cfg = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(exit_node.id),
            NodeProtocolConfig.protocol == "v2ray",
        )
        .first()
    )
    if (
        not bool(getattr(exit_node, "enable_v2ray", False))
        or cfg is None
        or _enum_value(cfg.status) != "online"
    ):
        return {"ok": True, "skipped": True, "reason": "exit_xray_not_online"}

    cred, items = _stored_items(db, int(sub.id))
    by_node = _items_by_node(items)
    previous = by_node.get(int(exit_node.id))
    if _item_complete_for_node(previous, exit_node):
        return {"ok": True, "skipped": True, "reason": "already_complete"}

    user = db.get(User, int(sub.user_id))
    if user is None:
        raise RuntimeError("subscription_user_missing")

    client_id = xray_modern_runtime._existing_uuid(previous) or str(uuid.uuid4())
    item = await xray_modern_runtime._xray_account_modern(
        db,
        exit_node,
        sub,
        user,
        client_id,
    )
    by_node[int(exit_node.id)] = item

    if cred is None:
        cred = ProtocolCredential(
            subscription_id=int(sub.id),
            protocol="v2ray",
        )
        db.add(cred)

    ordered = [
        by_node[node_id]
        for node_id in sorted(by_node)
        if isinstance(by_node[node_id], dict)
    ]
    cred.config_text_encrypted = account_delivery._enc(ordered)
    cred.is_active = True
    db.commit()

    return {
        "ok": True,
        "skipped": False,
        "node_id": int(exit_node.id),
        "profiles": sorted(_profile_ids(item)),
        "uuid_preserved": bool(previous),
    }


def _cleanup_jobs() -> None:
    now = time.time()
    stale = [
        job_id
        for job_id, item in _jobs.items()
        if now - float(item.get("created_at_epoch") or now) > _JOB_TTL_SECONDS
    ]
    for job_id in stale:
        item = _jobs.pop(job_id, None)
        if not item:
            continue
        exit_id = int(item.get("exit_node_id") or 0)
        if _running_by_exit.get(exit_id) == job_id:
            _running_by_exit.pop(exit_id, None)


async def _run_reconcile_job(job_id: str, exit_node_id: int) -> None:
    db = SessionLocal()
    try:
        job = _jobs[job_id]
        job["status"] = "running"
        job["started_at_epoch"] = time.time()

        exit_node = db.get(Node, int(exit_node_id))
        if exit_node is None or exit_node.node_type != NodeType.EXIT:
            raise RuntimeError("exit_node_not_found")

        subscription_ids = sorted(
            {
                int(row[0])
                for row in (
                    db.query(SubscriptionProtocol.subscription_id)
                    .filter(SubscriptionProtocol.protocol == "v2ray")
                    .all()
                )
            }
        )
        migrated = 0
        skipped = 0
        errors: list[dict[str, Any]] = []
        job["total"] = len(subscription_ids)

        for index, subscription_id in enumerate(subscription_ids, start=1):
            sub = db.get(Subscription, int(subscription_id))
            if sub is None:
                skipped += 1
                continue
            try:
                result = await _reconcile_subscription_for_exit(db, sub, exit_node)
                if result.get("skipped"):
                    skipped += 1
                else:
                    migrated += 1
            except Exception as exc:
                db.rollback()
                errors.append(
                    {
                        "subscription_id": int(subscription_id),
                        "error": str(exc)[:1000],
                    }
                )

            job["processed"] = index
            job["migrated"] = migrated
            job["skipped"] = skipped
            job["errors"] = list(errors)

        job["status"] = "succeeded" if not errors else "completed_with_errors"
        job["finished_at_epoch"] = time.time()
        job["result"] = {
            "ok": not errors,
            "exit_node_id": int(exit_node_id),
            "total": len(subscription_ids),
            "migrated": migrated,
            "skipped": skipped,
            "errors": errors,
        }
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        job = _jobs.get(job_id)
        if job is not None:
            job["status"] = "failed"
            job["finished_at_epoch"] = time.time()
            job["error"] = str(exc)[:1500]
    finally:
        async with _job_lock:
            if _running_by_exit.get(int(exit_node_id)) == job_id:
                _running_by_exit.pop(int(exit_node_id), None)
        db.close()


async def start_xray_reconcile_job(exit_node_id: int) -> dict[str, Any]:
    async with _job_lock:
        _cleanup_jobs()
        existing = _running_by_exit.get(int(exit_node_id))
        if existing and existing in _jobs:
            return dict(_jobs[existing])

        job_id = uuid.uuid4().hex
        item = {
            "job_id": job_id,
            "exit_node_id": int(exit_node_id),
            "status": "queued",
            "created_at_epoch": time.time(),
            "processed": 0,
            "total": 0,
            "migrated": 0,
            "skipped": 0,
            "errors": [],
        }
        _jobs[job_id] = item
        _running_by_exit[int(exit_node_id)] = job_id
        asyncio.create_task(_run_reconcile_job(job_id, int(exit_node_id)))
        return dict(item)


def get_xray_reconcile_job(job_id: str, exit_node_id: int) -> dict[str, Any]:
    _cleanup_jobs()
    item = _jobs.get(str(job_id))
    if item is None or int(item.get("exit_node_id") or 0) != int(exit_node_id):
        raise HTTPException(status_code=404, detail="Xray reconciliation job not found")
    return dict(item)


def apply_xray_profile_reconcile_v36() -> None:
    global _runtime_applied
    global _original_ensure_subscription_modern
    if _runtime_applied:
        return

    _original_ensure_subscription_modern = xray_modern_runtime._ensure_subscription_modern
    xray_modern_runtime._ensure_subscription_modern = _ensure_subscription_modern_v36
    _runtime_applied = True
    print(
        "TWINPANEL_XRAY_PROFILE_RECONCILE_V36_ACTIVE "
        "uuid_preserved=1 tls_profile_completeness=1",
        flush=True,
    )
