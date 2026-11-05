"""Central volume reseller tier policy.

A tier determines allowed public-plan server/protocol sets. Traffic is still a
single usage pool; no subscription billing or additional balance is created.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Node, NodeType, Plan
from .models_reseller import Reseller, ResellerTrafficPackage
from .plan_category_models import PlanCategoryAssignment
from .plan_node_models import PlanNode
from .plan_protocol_models import PlanProtocol
from .protocol_account_registry import normalize_protocols

ECONOMIC = "economic_v2ray"
PREMIUM = "premium_static_ip"
TIERS = (ECONOMIC, PREMIUM)
TIER_LABELS = {
    ECONOMIC: "اشتراک اقتصادی ویتوری",
    PREMIUM: "اشتراک ویژه آی پی ثابت",
}


def valid_tier(value: str) -> str:
    value = str(value or "").strip()
    if value not in TIERS:
        raise HTTPException(status_code=422, detail="نوع نمایندگی باید اقتصادی یا ویژه باشد")
    return value


def reseller_tier(reseller: Reseller) -> str:
    # Existing reseller rows are migrated to premium, preserving sales/pool.
    return valid_tier(getattr(reseller, "reseller_tier", PREMIUM))


def tier_entitlements(db: Session, tier: str) -> dict:
    tier = valid_tier(tier)
    plan_ids = [
        int(row[0])
        for row in db.query(Plan.id)
        .join(PlanCategoryAssignment, PlanCategoryAssignment.plan_id == Plan.id)
        .filter(
            Plan.is_active.is_(True),
            PlanCategoryAssignment.subscription_type == TIER_LABELS[tier],
        ).all()
    ]
    if not plan_ids:
        raise HTTPException(
            status_code=409,
            detail="هیچ پلن فعالی برای این نوع نمایندگی تعریف نشده است",
        )
    protocols = sorted({
        str(row[0]).strip().lower()
        for row in db.query(PlanProtocol.protocol)
        .filter(PlanProtocol.plan_id.in_(plan_ids)).all()
    })
    # Strictly use explicit PlanNode rules, never fall back to all exits.
    node_ids = sorted({
        int(row[0])
        for row in db.query(PlanNode.node_id)
        .join(Node, Node.id == PlanNode.node_id)
        .filter(
            PlanNode.plan_id.in_(plan_ids),
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
        ).all()
    })
    if not protocols or not node_ids:
        raise HTTPException(
            status_code=409,
            detail="سرور یا پروتکل مجاز این نوع نمایندگی تعریف نشده است",
        )
    return {
        "tier": tier,
        "title": TIER_LABELS[tier],
        "protocols": protocols,
        "node_ids": node_ids,
    }


def check_package_tier(reseller: Reseller, package: ResellerTrafficPackage) -> None:
    if reseller_tier(reseller) != valid_tier(package.reseller_tier):
        raise HTTPException(
            status_code=403,
            detail="این بسته حجم متعلق به نوع نمایندگی شما نیست",
        )


def allowed_protocols(db: Session, reseller: Reseller, requested: list[str] | None) -> list[str]:
    allowed = set(tier_entitlements(db, reseller_tier(reseller))["protocols"])
    try:
        requested_values = normalize_protocols(requested or [])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not requested_values:
        return sorted(allowed)
    invalid = sorted(set(requested_values) - allowed)
    if invalid:
        raise HTTPException(
            status_code=403,
            detail="پروتکل خارج از نوع نمایندگی مجاز نیست: " + ", ".join(invalid),
        )
    return requested_values


def allowed_nodes(db: Session, reseller: Reseller, requested: list[int] | None) -> list[int]:
    allowed = set(tier_entitlements(db, reseller_tier(reseller))["node_ids"])
    requested_ids = list(dict.fromkeys(int(x) for x in (requested or [])))
    if not requested_ids:
        return sorted(allowed)
    invalid = sorted(set(requested_ids) - allowed)
    if invalid:
        raise HTTPException(
            status_code=403,
            detail="سرور خارج از نوع نمایندگی مجاز نیست: " + ", ".join(map(str, invalid)),
        )
    return requested_ids


def assert_plan_tier(db: Session, reseller: Reseller, plan_id: int) -> None:
    # Public assigned plans must belong to the reseller's permitted type.
    # Internal reseller-owned backing plans are constrained at creation.
    plan = db.get(Plan, int(plan_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    if str(plan.name or "").startswith("__tp_reseller__"):
        return
    assignment = db.query(PlanCategoryAssignment).filter(
        PlanCategoryAssignment.plan_id == int(plan_id)
    ).first()
    if not assignment or assignment.subscription_type != TIER_LABELS[reseller_tier(reseller)]:
        raise HTTPException(status_code=403, detail="پلن خارج از نوع نمایندگی مجاز نیست")


def tier_out(db: Session, reseller: Reseller) -> dict:
    return {
        "reseller_tier": reseller_tier(reseller),
        "tier_title": TIER_LABELS[reseller_tier(reseller)],
        "tier_entitlements": tier_entitlements(db, reseller_tier(reseller)),
    }
