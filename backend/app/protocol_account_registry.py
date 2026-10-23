from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from .plan_protocol_models import PlanProtocol


CLASSIC_PROTOCOL_KEYS = (
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
)

MODERN_PROTOCOL_KEYS = (
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
)

ALL_PROTOCOL_KEYS = CLASSIC_PROTOCOL_KEYS + MODERN_PROTOCOL_KEYS
ALL_PROTOCOL_SET = frozenset(ALL_PROTOCOL_KEYS)

PROTOCOL_ALIASES = {
    "openconnect": "cisco",
    "xray": "v2ray",
    "naiveproxy": "naive",
    "l2tp/ipsec": "l2tp",
}

CLASSIC_PLAN_FIELDS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}

PROTOCOL_TITLES = {
    "cisco": "Cisco / OpenConnect",
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "l2tp": "L2TP / IPsec",
    "v2ray": "V2Ray / Xray",
    "hysteria2": "Hysteria2",
    "tuic": "TUIC",
    "anytls": "AnyTLS",
    "naive": "NaiveProxy",
    "shadowtls": "ShadowTLS",
    "snell": "Snell",
    "mieru": "Mieru",
    "trusttunnel": "TrustTunnel",
    "amneziawg": "AmneziaWG",
    "sudoku": "Sudoku",
}


def canonical_protocol(value: str) -> str:
    key = str(value or "").strip().lower()
    key = PROTOCOL_ALIASES.get(key, key)
    if key not in ALL_PROTOCOL_SET:
        raise ValueError(f"unsupported protocol: {value}")
    return key


def normalize_protocols(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for raw in values or ():
        key = canonical_protocol(raw)
        if key not in result:
            result.append(key)
    return result


def legacy_plan_protocols(plan: Any) -> list[str]:
    return [
        protocol
        for protocol, field in CLASSIC_PLAN_FIELDS.items()
        if bool(getattr(plan, field, False))
    ]


def explicit_plan_protocols(db: Session, plan_id: int) -> list[str]:
    values = [
        str(row[0]).strip().lower()
        for row in (
            db.query(PlanProtocol.protocol)
            .filter(PlanProtocol.plan_id == int(plan_id))
            .order_by(PlanProtocol.id.asc())
            .all()
        )
    ]
    present = set(values)
    return [key for key in ALL_PROTOCOL_KEYS if key in present]


def plan_protocols(db: Session, plan: Any) -> list[str]:
    explicit = explicit_plan_protocols(db, int(plan.id))
    if explicit:
        return explicit
    return legacy_plan_protocols(plan)


def replace_plan_protocols(
    db: Session,
    plan_id: int,
    protocols: Iterable[str],
) -> list[str]:
    values = normalize_protocols(protocols)
    if not values:
        raise ValueError("at least one protocol is required")

    db.query(PlanProtocol).filter(
        PlanProtocol.plan_id == int(plan_id)
    ).delete(synchronize_session=False)

    for protocol in values:
        db.add(PlanProtocol(plan_id=int(plan_id), protocol=protocol))

    db.flush()
    return values


def registry_payload() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "title": PROTOCOL_TITLES[key],
            "family": "classic" if key in CLASSIC_PLAN_FIELDS else "modern",
        }
        for key in ALL_PROTOCOL_KEYS
    ]
