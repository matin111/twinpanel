import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import Plan, Subscription, SubscriptionStatus
from .quota_models import (
    QuotaCursor,
    QuotaDevice,
    QuotaNodeCommand,
    QuotaSession,
    QuotaUsageEvent,
)
from .quota_schemas import CommandAckIn, SessionCloseIn, SessionOpenIn, UsageEventIn
from .quota_security import advisory_key, sign_command
from .subscription_enforcement import queue_subscription_enforcement


MAX_BIGINT = 2**63 - 1


def _lock(db: Session, namespace: str, value: str) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": advisory_key(namespace, value)})


def _counter_delta(data: UsageEventIn, cursor: QuotaCursor | None, epoch_changed: bool) -> tuple[int, int]:
    if data.counter_mode == "delta" or cursor is None or epoch_changed:
        up_delta, down_delta = data.uplink_value, data.downlink_value
    else:
        if data.uplink_value < cursor.last_uplink_value or data.downlink_value < cursor.last_downlink_value:
            raise HTTPException(status_code=409, detail="counter_decreased_without_new_epoch")
        up_delta = data.uplink_value - cursor.last_uplink_value
        down_delta = data.downlink_value - cursor.last_downlink_value
    if up_delta + down_delta > MAX_BIGINT:
        raise HTTPException(status_code=409, detail="counter_overflow")
    return up_delta, down_delta


def apply_usage_event(db: Session, node_id: int, data: UsageEventIn) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reported_at = data.reported_at.astimezone(timezone.utc).replace(tzinfo=None)
    if reported_at > now + timedelta(minutes=5):
        raise HTTPException(status_code=409, detail="agent_clock_ahead")

    _lock(db, "quota-event", data.event_id)
    existing = db.scalar(select(QuotaUsageEvent).where(QuotaUsageEvent.event_id == data.event_id))
    if existing:
        same = (
            existing.node_id == node_id
            and existing.subscription_id == data.subscription_id
            and existing.device_id == data.device_id
            and existing.session_key == data.session_key
            and existing.protocol == data.protocol
            and existing.source_key == data.source_key
            and existing.counter_mode == data.counter_mode
            and existing.counter_epoch == data.counter_epoch
            and existing.source_sequence == data.source_sequence
            and existing.raw_uplink_value == data.uplink_value
            and existing.raw_downlink_value == data.downlink_value
        )
        if not same:
            raise HTTPException(status_code=409, detail="usage_event_id_conflict")
        return {
            "event_id": existing.event_id,
            "duplicate": True,
            "billable_bytes": existing.billable_bytes,
            "accepted_bytes": existing.accepted_bytes,
            "overage_bytes": existing.overage_bytes,
            "subscription_status": existing.resulting_subscription_status,
            "disconnect_commands_created": 0,
        }

    _lock(db, "quota-source", f"{node_id}:{data.source_key}")
    cursor = db.scalar(
        select(QuotaCursor).where(
            QuotaCursor.node_id == node_id,
            QuotaCursor.source_key == data.source_key,
        )
    )
    if cursor and (
        cursor.subscription_id != data.subscription_id
        or cursor.device_id != data.device_id
        or cursor.protocol != data.protocol
        or cursor.counter_mode != data.counter_mode
    ):
        raise HTTPException(status_code=409, detail="counter_source_identity_changed")

    epoch_changed = bool(cursor and cursor.counter_epoch != data.counter_epoch)
    if epoch_changed:
        reused = db.scalar(
            select(QuotaUsageEvent.id)
            .where(
                QuotaUsageEvent.node_id == node_id,
                QuotaUsageEvent.source_key == data.source_key,
                QuotaUsageEvent.counter_epoch == data.counter_epoch,
            )
            .limit(1)
        )
        if reused:
            raise HTTPException(status_code=409, detail="counter_epoch_reused")
    if cursor and not epoch_changed and data.source_sequence <= cursor.last_sequence:
        raise HTTPException(status_code=409, detail="source_sequence_replayed")

    subscription = db.scalar(
        select(Subscription).where(Subscription.id == data.subscription_id).with_for_update()
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    device = db.get(QuotaDevice, data.device_id)
    if device is None or device.subscription_id != subscription.id:
        raise HTTPException(status_code=409, detail="device_subscription_mismatch")

    up_delta, down_delta = _counter_delta(data, cursor, epoch_changed)
    billable = up_delta + down_delta
    used_before = max(int(subscription.traffic_used_bytes or 0), 0)
    limit = max(int(subscription.traffic_limit_bytes or 0), 0)
    blocked = subscription.status != SubscriptionStatus.ACTIVE
    if subscription.expires_at and subscription.expires_at <= now:
        blocked = True
        subscription.status = SubscriptionStatus.EXPIRED

    if blocked:
        accepted, overage, new_used = 0, billable, used_before
    elif limit == 0:
        accepted, overage, new_used = billable, 0, used_before + billable
    else:
        remaining = max(limit - used_before, 0)
        accepted = min(remaining, billable)
        overage = billable - accepted
        new_used = used_before + accepted

    became_exhausted = not blocked and limit > 0 and new_used >= limit
    subscription.traffic_used_bytes = new_used
    if became_exhausted:
        subscription.status = SubscriptionStatus.SUSPENDED

    if cursor is None:
        cursor = QuotaCursor(
            node_id=node_id,
            subscription_id=subscription.id,
            device_id=device.id,
            protocol=data.protocol,
            source_key=data.source_key,
            counter_mode=data.counter_mode,
            counter_epoch=data.counter_epoch,
            last_sequence=data.source_sequence,
            last_uplink_value=data.uplink_value,
            last_downlink_value=data.downlink_value,
        )
        db.add(cursor)
    else:
        cursor.counter_epoch = data.counter_epoch
        cursor.last_sequence = data.source_sequence
        cursor.last_uplink_value = data.uplink_value
        cursor.last_downlink_value = data.downlink_value
        cursor.updated_at = now

    resulting_status = subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)
    db.add(
        QuotaUsageEvent(
            event_id=data.event_id,
            subscription_id=subscription.id,
            node_id=node_id,
            device_id=device.id,
            session_key=data.session_key,
            protocol=data.protocol,
            source_key=data.source_key,
            counter_mode=data.counter_mode,
            counter_epoch=data.counter_epoch,
            source_sequence=data.source_sequence,
            raw_uplink_value=data.uplink_value,
            raw_downlink_value=data.downlink_value,
            uplink_delta=up_delta,
            downlink_delta=down_delta,
            billable_bytes=billable,
            accepted_bytes=accepted,
            overage_bytes=overage,
            resulting_subscription_status=resulting_status,
            reported_at=reported_at,
        )
    )

    command_count = 0
    revoke_command_count = 0

    if became_exhausted:
        # TWINPANEL_QUOTA_PERSISTENT_REVOKE_V1
        #
        # Quota exhaustion must revoke the
        # subscription identity itself, not only
        # terminate currently open sessions.
        #
        # Each protocol handler also receives its
        # currently known active session keys.
        enforcement = (
            queue_subscription_enforcement(
                db,
                subscription,
                command_type=
                    "revoke_subscription",
                reason=
                    "quota_exhausted",
            )
        )

        revoke_command_count = int(
            enforcement[
                "commands_created"
            ]
        )

        # Keep the legacy response field for
        # API compatibility.
        command_count = (
            revoke_command_count
        )

    db.flush()
    return {
        "event_id": data.event_id,
        "duplicate": False,
        "billable_bytes": billable,
        "accepted_bytes": accepted,
        "overage_bytes": overage,
        "quota_bytes_used": new_used,
        "quota_bytes_total": limit or None,
        "subscription_status": resulting_status,
        "disconnect_commands_created": command_count,
        "revoke_commands_created": revoke_command_count,
    }


def open_session(db: Session, node_id: int, data: SessionOpenIn) -> dict:
    _lock(db, "quota-session", f"{node_id}:{data.session_key}")
    existing = db.scalar(
        select(QuotaSession).where(
            QuotaSession.node_id == node_id,
            QuotaSession.session_key == data.session_key,
        )
    )
    if existing:
        if existing.status != "active" or existing.subscription_id != data.subscription_id:
            raise HTTPException(status_code=409, detail="session_key_conflict")
        return {"session_id": existing.id, "duplicate": True, "status": existing.status}

    subscription = db.scalar(
        select(Subscription).where(Subscription.id == data.subscription_id).with_for_update()
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    now = datetime.utcnow()
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="subscription_not_active")
    if subscription.expires_at and subscription.expires_at <= now:
        raise HTTPException(status_code=403, detail="subscription_expired")
    limit = max(int(subscription.traffic_limit_bytes or 0), 0)
    used = max(int(subscription.traffic_used_bytes or 0), 0)
    if limit > 0 and used >= limit:
        raise HTTPException(status_code=403, detail="subscription_quota_exhausted")

    device = db.get(QuotaDevice, data.device_id)
    if device is None or device.subscription_id != subscription.id or device.status != "active":
        raise HTTPException(status_code=403, detail="device_not_allowed")
    plan = db.get(Plan, subscription.plan_id)
    max_sessions = max(int(plan.device_limit if plan else 1), 1)
    active_count = int(
        db.scalar(
            select(func.count(QuotaSession.id)).where(
                QuotaSession.subscription_id == subscription.id,
                QuotaSession.status == "active",
            )
        )
        or 0
    )
    if active_count >= max_sessions:
        raise HTTPException(status_code=409, detail="concurrent_session_limit")

    # TWINPANEL_FIRST_USE_ACTIVATION_V1
    # The Subscription row is already locked FOR UPDATE above.
    # Start the time period only after this session has passed
    # status, expiry, quota, device and concurrency validation.
    if (
        subscription.starts_at is None
        and subscription.expires_at is None
    ):
        duration_days = int(
            subscription.activation_duration_days
            or (
                plan.duration_days
                if plan
                else 0
            )
            or 0
        )

        if duration_days <= 0:
            raise HTTPException(
                status_code=409,
                detail="subscription_activation_duration_missing",
            )

        subscription.activation_duration_days = duration_days
        subscription.starts_at = now
        subscription.expires_at = (
            now
            + timedelta(
                days=duration_days
            )
        )

        db.flush()

    vpn_session = QuotaSession(
        session_key=data.session_key,
        subscription_id=subscription.id,
        device_id=device.id,
        node_id=node_id,
        protocol=data.protocol,
        status="active",
        client_ip=data.client_ip,
        started_at=now,
        last_seen_at=now,
    )
    db.add(vpn_session)
    db.flush()
    return {
        "session_id": vpn_session.id,
        "duplicate": False,
        "status": vpn_session.status,
        "active_sessions": active_count + 1,
        "max_concurrent_sessions": max_sessions,
    }


def close_session(db: Session, node_id: int, data: SessionCloseIn) -> dict:
    _lock(db, "quota-session", f"{node_id}:{data.session_key}")
    vpn_session = db.scalar(
        select(QuotaSession).where(
            QuotaSession.node_id == node_id,
            QuotaSession.session_key == data.session_key,
        ).with_for_update()
    )
    if vpn_session is None:
        return {"session_id": None, "duplicate": True, "status": "closed"}
    if vpn_session.status != "active":
        return {"session_id": vpn_session.id, "duplicate": True, "status": vpn_session.status}
    vpn_session.status = "closed"
    vpn_session.ended_at = datetime.utcnow()
    vpn_session.last_seen_at = datetime.utcnow()
    vpn_session.close_reason = data.reason
    return {"session_id": vpn_session.id, "duplicate": False, "status": "closed"}


def pull_commands(db: Session, node_id: int, limit: int) -> list[dict]:
    now = datetime.utcnow()
    commands = db.scalars(
        select(QuotaNodeCommand)
        .where(
            QuotaNodeCommand.node_id == node_id,
            QuotaNodeCommand.status == "pending",
            QuotaNodeCommand.expires_at > now,
        )
        .order_by(QuotaNodeCommand.issued_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    output = []
    for command in commands:
        expires_at = min(command.expires_at, now + timedelta(seconds=90))
        unsigned = {
            "version": 1,
            "command_id": command.command_id,
            "node_id": command.node_id,
            "command_type": command.command_type,
            "payload": command.payload,
            "nonce": command.nonce,
            "issued_at": now.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "expires_at": expires_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        output.append({**unsigned, "signature": sign_command(unsigned)})
        command.last_delivered_at = now
        command.attempt_count += 1
    return output


def acknowledge_command(db: Session, node_id: int, command_id: str, data: CommandAckIn) -> dict:
    command = db.scalar(
        select(QuotaNodeCommand).where(
            QuotaNodeCommand.node_id == node_id,
            QuotaNodeCommand.command_id == command_id,
        ).with_for_update()
    )
    if command is None:
        raise HTTPException(status_code=404, detail="command_not_found")
    if command.status in {"succeeded", "failed", "rejected"}:
        if command.status != data.status or command.result_code != data.result_code:
            raise HTTPException(status_code=409, detail="command_ack_conflict")
        return {"command_id": command_id, "duplicate": True, "status": command.status}
    command.status = data.status
    command.result_code = data.result_code
    command.result_message = data.result_message
    command.acknowledged_at = datetime.utcnow()
    return {"command_id": command_id, "duplicate": False, "status": command.status}
