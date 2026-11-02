from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, object_session

from ..database import get_db
from ..deps import require_reseller
from ..models import Node, NodeProtocolConfig, NodeType
from ..models_reseller import Reseller
from ..plan_template_selection import plan_template_protocols
from ..protocol_account_registry import normalize_protocols
from ..services.subscription_provision_preflight_v1 import (
    CLASSIC_NODE_FLAGS,
    MODERN_PROTOCOLS,
)
from . import reseller_sale_v2
from . import subscription_create_fast_v1
from .modern_account_delivery_v1 import provision_account_v1
from .reseller_sale_v2 import ResellerSaleV2In


router = APIRouter(tags=["account-creation-runtime-v4"])


def advisory_subscription_provisioning_preflight(
    db: Session,
    protocols: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Require at least one usable requested protocol, not every protocol.

    Account Delivery intentionally supports degraded/partial provisioning: one
    unavailable protocol must not block creation when other selected protocols
    are healthy. The old fast-create preflight required every selected protocol
    to be ready and contradicted the post-provisioning partial-delivery policy.
    """

    requested = normalize_protocols(protocols)
    if not requested:
        raise HTTPException(status_code=422, detail="حداقل یک پروتکل انتخاب کنید")

    exits = (
        db.query(Node)
        .filter(
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
        )
        .order_by(Node.id.asc())
        .all()
    )
    if not exits:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "subscription_provision_no_exit",
                "message": "هیچ سرور خروجی فعالی برای ساخت اشتراک وجود ندارد",
            },
        )

    exit_ids = [int(node.id) for node in exits]
    ready_nodes: dict[str, list[int]] = {}
    unavailable: list[dict[str, Any]] = []

    for protocol in requested:
        if protocol in CLASSIC_NODE_FLAGS:
            flag = CLASSIC_NODE_FLAGS[protocol]
            node_ids = [
                int(node.id)
                for node in exits
                if bool(getattr(node, flag, False))
            ]
        elif protocol in MODERN_PROTOCOLS:
            online_ids = {
                int(row[0])
                for row in (
                    db.query(NodeProtocolConfig.node_id)
                    .filter(
                        NodeProtocolConfig.node_id.in_(exit_ids),
                        NodeProtocolConfig.protocol == protocol,
                        NodeProtocolConfig.status == "online",
                    )
                    .all()
                )
            }
            node_ids = [int(node.id) for node in exits if int(node.id) in online_ids]
        else:
            node_ids = []

        ready_nodes[protocol] = node_ids
        if not node_ids:
            unavailable.append(
                {
                    "protocol": protocol,
                    "reason": (
                        "no_enabled_exit"
                        if protocol in CLASSIC_NODE_FLAGS
                        else "no_online_runtime"
                    ),
                }
            )

    ready_protocols = [protocol for protocol in requested if ready_nodes.get(protocol)]
    if not ready_protocols:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "subscription_provision_preflight_failed",
                "message": "هیچ‌کدام از پروتکل‌های انتخاب‌شده روی Exit آماده نیستند",
                "unavailable_protocols": unavailable,
                "ready_nodes": ready_nodes,
            },
        )

    return {
        "ok": True,
        "degraded": bool(unavailable),
        "protocols": requested,
        "ready_protocols": ready_protocols,
        "unavailable_protocols": unavailable,
        "ready_nodes": ready_nodes,
    }


def reseller_plan_protocols_v4(plan, payload) -> list[str]:
    """Resolve reseller protocols from the canonical 15-protocol plan template."""

    db = object_session(plan)
    if db is None:
        raise HTTPException(status_code=500, detail="جلسه دیتابیس پلن در دسترس نیست")

    allowed = list(plan_template_protocols(db, int(plan.id)))
    if not allowed:
        raise HTTPException(
            status_code=422,
            detail="برای این پلن پروتکل فعالی تعریف نشده است",
        )

    try:
        requested = normalize_protocols(
            list(getattr(payload, "protocols", []) or [])
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not requested:
        return allowed

    invalid = [protocol for protocol in requested if protocol not in allowed]
    if invalid:
        raise HTTPException(
            status_code=403,
            detail="پروتکل خارج از پلن مجاز است: " + ", ".join(invalid),
        )
    return requested


@router.post("/v1/reseller/subscriptions/sell")
async def reseller_sell_and_provision_v4(
    payload: ResellerSaleV2In,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    """Make the reseller panel sale path create real protocol accounts too.

    Telegram orders already provision after their DB sale step. The direct panel
    endpoint previously stopped after create_subscription_core(), leaving a
    DB-only subscription. Runtime route precedence makes this the canonical
    direct-panel endpoint while the bot compatibility helper remains unchanged.
    """

    sale = reseller_sale_v2._sale_impl(
        payload,
        reseller=reseller,
        db=db,
    )
    subscription_id = int(sale["subscription_id"])

    try:
        provisioning = await provision_account_v1(
            subscription_id=subscription_id,
            db=db,
        )
    except HTTPException as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "اشتراک ثبت شد اما ساخت اکانت روی سرورها کامل نشد",
                "subscription_id": subscription_id,
                "provision_error": exc.detail,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "اشتراک ثبت شد اما Provisioning با خطا مواجه شد",
                "subscription_id": subscription_id,
                "provision_error": str(exc)[:800],
            },
        ) from exc

    warnings = list(provisioning.get("errors") or []) if isinstance(provisioning, dict) else []
    return {
        **sale,
        "provisioning_complete": True,
        "provisioning_ok": bool(isinstance(provisioning, dict) and provisioning.get("ok", False)),
        "provision_warnings": warnings,
    }


def install_account_creation_runtime_v4() -> None:
    # The fast-create endpoint resolves this global at request time. Replace its
    # all-or-nothing readiness gate with the same degraded-delivery semantics
    # already used after provisioning.
    subscription_create_fast_v1.assert_subscription_provisioning_ready = (
        advisory_subscription_provisioning_preflight
    )

    # _sale_impl resolves this module global at request time. This upgrades both
    # direct reseller sales and legacy bot compatibility to the canonical plan
    # template without rewriting the historical sale/accounting implementation.
    reseller_sale_v2._resolve_protocols = reseller_plan_protocols_v4
