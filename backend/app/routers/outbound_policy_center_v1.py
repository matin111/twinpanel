from __future__ import annotations

import base64
import json
import shlex
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..node_runtime_connection import connect_protocol_runtime
from ..protocol_account_registry import ALL_PROTOCOL_KEYS, PROTOCOL_TITLES
from ..protocol_adapter_registry import CLASSIC_PROTOCOL_REGISTRY
from ..protocol_catalog import PROTOCOL_CATALOG
from .singbox_outbounds import (
    CONFIG_PATH,
    SERVICE_NAME,
    _inventory_from_document,
    _node,
    _read_document,
)


POLICY_STATE_PATH = "/etc/twinpanel/sing-box/outbound-policy.json"
POLICY_SCHEMA = 1

router = APIRouter(
    prefix="/v1/settings/vpn/outbound-policy",
    tags=["outbound-policy-center-v1"],
    dependencies=[Depends(require_admin)],
)


# Inventory comes from TwinPanel's canonical protocol registry so the routing
# surface cannot silently drift behind the protocols offered elsewhere in the
# product. Routing capability remains deliberately narrower: only protocols
# whose traffic is already an audited, identifiable Sing-box inbound are
# writable. Everything else is visible but fail-closed until a dedicated
# egress adapter is implemented and verified.
_NATIVE_POLICY_PROTOCOLS: dict[str, str] = {
    "hysteria2": "twinpanel-hysteria2-in",
    "tuic": "twinpanel-tuic-in",
    "anytls": "twinpanel-anytls-in",
    "naive": "twinpanel-naive-in",
    # ShadowTLS is a camouflage/authentication layer. Customer payload enters
    # the internal Shadowsocks inbound after ShadowTLS succeeds, so policy must
    # attach to the inner inbound rather than the outer TLS listener.
    "shadowtls": "twinpanel-shadowtls-inner",
    "snell": "twinpanel-snell-in",
}

# Xray currently exposes real customer VLESS profiles, but its data plane is a
# separate core. Keep those profiles visible as independent routing rows so the
# admin sees the actual product surface, while fail-closing writes until an
# audited Xray egress adapter exists.
_XRAY_PROFILE_PROTOCOLS: dict[str, dict[str, str]] = {
    "vless_ws_tls": {"title": "VLESS · WebSocket TLS", "profile": "websocket_tls"},
    "vless_httpupgrade_tls": {"title": "VLESS · HTTPUpgrade TLS", "profile": "httpupgrade_tls"},
    "vless_tcp_tls": {"title": "VLESS · TCP TLS", "profile": "tcp_tls"},
    "vless_xhttp_reality": {"title": "VLESS · XHTTP Reality", "profile": "xhttp_reality"},
    "vless_grpc_reality": {"title": "VLESS · gRPC Reality", "profile": "grpc_reality"},
    "vless_tcp_simple": {"title": "VLESS · TCP Simple", "profile": "tcp_simple"},
    "vless_legacy": {"title": "VLESS · Legacy / Admin", "profile": "legacy"},
}

_POLICY_ALIASES = {
    "xray": "v2ray",
}

_NATIVE_ORDER: tuple[str, ...] = (
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
)
_CLASSIC_ORDER: tuple[str, ...] = (
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
)
_PROTOCOL_ORDER: tuple[str, ...] = (
    *_NATIVE_ORDER,
    *_CLASSIC_ORDER,
    *_XRAY_PROFILE_PROTOCOLS.keys(),
    *(
        key
        for key in ALL_PROTOCOL_KEYS
        if key not in set(_NATIVE_ORDER) | set(_CLASSIC_ORDER)
    ),
)


def _protocol_spec(key: str) -> dict[str, Any]:
    xray_profile = _XRAY_PROFILE_PROTOCOLS.get(key)
    if xray_profile is not None:
        return {
            "key": key,
            "title": xray_profile["title"],
            "family": "xray_profile",
            "plane": "xray",
            "core": "xray",
            "runtime_status": "profile",
            "profile": xray_profile["profile"],
            "inbound_tag": None,
            "policy_supported": False,
            "reason": "separate_core_adapter_required",
        }

    if key in CLASSIC_PROTOCOL_REGISTRY:
        definition = CLASSIC_PROTOCOL_REGISTRY[key]
        plane = "xray" if key == "v2ray" else "kernel"
        reason = "separate_core_adapter_required" if key == "v2ray" else "egress_adapter_required"
        core = str(definition.get("core") or PROTOCOL_TITLES[key])
        runtime_status = str(definition.get("runtime_status") or "unknown")
        title = str(definition.get("title") or PROTOCOL_TITLES[key])
        family = "classic"
    else:
        definition = PROTOCOL_CATALOG.get(key, {})
        core = str(definition.get("core") or "standalone")
        plane = "singbox" if core == "sing-box" else "standalone"
        reason = (
            "singbox_policy_adapter_required"
            if core == "sing-box"
            else "protocol_egress_adapter_required"
        )
        runtime_status = str(definition.get("runtime_status") or "unknown")
        title = str(definition.get("title") or PROTOCOL_TITLES[key])
        family = "modern"

    inbound_tag = _NATIVE_POLICY_PROTOCOLS.get(key)
    supported = inbound_tag is not None
    return {
        "key": key,
        "title": title,
        "family": family,
        "plane": plane,
        "core": core,
        "runtime_status": runtime_status,
        "inbound_tag": inbound_tag,
        "policy_supported": supported,
        "reason": None if supported else reason,
    }


_PROTOCOLS: tuple[dict[str, Any], ...] = tuple(
    _protocol_spec(key) for key in _PROTOCOL_ORDER
)
_PROTOCOL_BY_KEY = {str(item["key"]): item for item in _PROTOCOLS}
PolicyMode = Literal["inherit", "direct", "outbound", "block"]


class ProtocolPolicyIn(BaseModel):
    mode: PolicyMode
    outbound_tag: str | None = Field(default=None, min_length=1, max_length=63)


def _empty_state() -> dict[str, Any]:
    return {
        "schema": POLICY_SCHEMA,
        "policies": {},
        "generated_rules": [],
    }


def _clean_state(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_state()
    policies = raw.get("policies") if isinstance(raw.get("policies"), dict) else {}
    generated = raw.get("generated_rules") if isinstance(raw.get("generated_rules"), list) else []
    return {
        "schema": POLICY_SCHEMA,
        "policies": {
            str(key): dict(value)
            for key, value in policies.items()
            if isinstance(value, dict)
        },
        "generated_rules": [dict(item) for item in generated if isinstance(item, dict)],
    }


async def _read_state(conn) -> dict[str, Any]:
    result = await conn.run(
        f"cat {shlex.quote(POLICY_STATE_PATH)}",
        check=False,
    )
    if result.exit_status != 0 or not str(result.stdout or "").strip():
        return _empty_state()
    try:
        return _clean_state(json.loads(result.stdout))
    except Exception:
        # A corrupt policy sidecar must never make the Sing-box config
        # inaccessible. Read-only inventory fails back to no managed rules;
        # the next successful apply rewrites a valid sidecar.
        return _empty_state()


def _inbound_tags(doc: dict[str, Any]) -> set[str]:
    items = doc.get("inbounds") if isinstance(doc.get("inbounds"), list) else []
    return {
        str(item.get("tag") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("tag") or "").strip()
    }


def _outbound_tags(doc: dict[str, Any]) -> set[str]:
    items = doc.get("outbounds") if isinstance(doc.get("outbounds"), list) else []
    return {
        str(item.get("tag") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("tag") or "").strip()
    }


def _policy_record(state: dict[str, Any], protocol: str) -> dict[str, Any]:
    raw = state.get("policies") if isinstance(state.get("policies"), dict) else {}
    item = raw.get(protocol) if isinstance(raw, dict) else None
    # Preserve compatibility with any early V1 state that used the UI label
    # "xray" before the canonical account-registry key "v2ray" was adopted.
    if not isinstance(item, dict) and protocol == "v2ray" and isinstance(raw, dict):
        item = raw.get("xray")
    if not isinstance(item, dict):
        return {"mode": "inherit", "outbound_tag": None}
    mode = str(item.get("mode") or "inherit").strip().lower()
    if mode not in {"inherit", "direct", "outbound", "block"}:
        mode = "inherit"
    outbound_tag = str(item.get("outbound_tag") or "").strip() or None
    if mode != "outbound":
        outbound_tag = None
    return {"mode": mode, "outbound_tag": outbound_tag}


def _generated_rule(protocol: str, policy: dict[str, Any]) -> dict[str, Any] | None:
    protocol = _POLICY_ALIASES.get(protocol, protocol)
    spec = _PROTOCOL_BY_KEY.get(protocol)
    if not spec or not spec.get("policy_supported"):
        return None
    inbound_tag = str(spec.get("inbound_tag") or "").strip()
    if not inbound_tag:
        return None

    mode = str(policy.get("mode") or "inherit").strip().lower()
    if mode == "inherit":
        return None
    if mode == "block":
        return {
            "inbound": [inbound_tag],
            "action": "reject",
            "method": "default",
        }
    if mode == "direct":
        return {
            "inbound": [inbound_tag],
            "action": "route",
            "outbound": "direct",
        }
    if mode == "outbound":
        outbound_tag = str(policy.get("outbound_tag") or "").strip()
        if not outbound_tag:
            raise ValueError(f"outbound_tag_required:{protocol}")
        return {
            "inbound": [inbound_tag],
            "action": "route",
            "outbound": outbound_tag,
        }
    raise ValueError(f"unsupported_policy_mode:{mode}")


def _build_generated_rules(state: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for spec in _PROTOCOLS:
        key = str(spec["key"])
        if not spec.get("policy_supported"):
            continue
        rule = _generated_rule(key, _policy_record(state, key))
        if rule is not None:
            rules.append(rule)
    return rules


def _strip_previous_generated_rules(
    rules: list[Any],
    previous: list[dict[str, Any]],
) -> list[Any]:
    """Remove only exact rules recorded by our last successful apply.

    We deliberately do not delete rules just because they reference the same
    inbound. That would risk modifying unrelated user/legacy routing logic.
    """
    remaining: list[Any] = []
    pending = [dict(item) for item in previous]
    for item in rules:
        if isinstance(item, dict):
            match_index = next((i for i, old in enumerate(pending) if old == item), None)
            if match_index is not None:
                pending.pop(match_index)
                continue
        remaining.append(item)
    return remaining


def _apply_state_to_document(
    doc: dict[str, Any],
    state: dict[str, Any],
    previous_generated: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    fresh_doc = json.loads(json.dumps(doc))
    fresh_state = _clean_state(state)
    route = fresh_doc.get("route") if isinstance(fresh_doc.get("route"), dict) else {}
    existing_rules = route.get("rules") if isinstance(route.get("rules"), list) else []
    retained = _strip_previous_generated_rules(existing_rules, previous_generated)
    generated = _build_generated_rules(fresh_state)
    route["rules"] = generated + retained
    fresh_doc["route"] = route
    fresh_state["generated_rules"] = generated
    fresh_state["schema"] = POLICY_SCHEMA
    return fresh_doc, fresh_state


def _effective_outbound(
    *,
    policy: dict[str, Any],
    default_tag: str | None,
) -> str:
    mode = str(policy.get("mode") or "inherit")
    if mode == "direct":
        return "direct"
    if mode == "block":
        return "block"
    if mode == "outbound":
        return str(policy.get("outbound_tag") or "") or "invalid"
    return default_tag or "direct"


def _protocol_payload(
    *,
    doc: dict[str, Any],
    state: dict[str, Any],
    default_tag: str | None,
) -> list[dict[str, Any]]:
    installed_tags = _inbound_tags(doc)
    rows: list[dict[str, Any]] = []
    for spec in _PROTOCOLS:
        key = str(spec["key"])
        supported = bool(spec.get("policy_supported"))
        inbound_tag = str(spec.get("inbound_tag") or "").strip() or None
        installed: bool | None = None
        if inbound_tag:
            installed = inbound_tag in installed_tags
        policy = _policy_record(state, key)
        rows.append({
            "key": key,
            "title": spec["title"],
            "family": spec.get("family"),
            "plane": spec["plane"],
            "core": spec.get("core"),
            "runtime_status": spec.get("runtime_status"),
            "profile": spec.get("profile"),
            "inbound_tag": inbound_tag,
            "policy_supported": supported,
            "installed": installed,
            "reason": spec.get("reason"),
            "mode": policy["mode"],
            "outbound_tag": policy["outbound_tag"],
            "effective_outbound": _effective_outbound(
                policy=policy,
                default_tag=default_tag,
            ),
        })
    return rows


async def _apply_documents(
    conn,
    *,
    doc: dict[str, Any],
    state: dict[str, Any],
) -> None:
    doc_b64 = base64.b64encode(
        json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    ).decode("ascii")
    state_b64 = base64.b64encode(
        json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    ).decode("ascii")

    command = f'''set -eu
CONFIG={shlex.quote(CONFIG_PATH)}
STATE={shlex.quote(POLICY_STATE_PATH)}
SERVICE={shlex.quote(SERVICE_NAME)}
BIN=/usr/local/bin/twinpanel-sing-box
if [ ! -x "$BIN" ]; then BIN="$(command -v sing-box || true)"; fi
[ -n "$BIN" ] || {{ echo singbox_binary_missing >&2; exit 61; }}
[ -s "$CONFIG" ] || {{ echo singbox_config_missing >&2; exit 62; }}
mkdir -p "$(dirname "$STATE")"
STAMP="$(date +%Y%m%d-%H%M%S)-$$"
CONFIG_BACKUP="${{CONFIG}}.policy-backup-${{STAMP}}"
STATE_BACKUP="${{STATE}}.policy-backup-${{STAMP}}"
STATE_EXISTED=0
cp -a "$CONFIG" "$CONFIG_BACKUP"
if [ -e "$STATE" ]; then cp -a "$STATE" "$STATE_BACKUP"; STATE_EXISTED=1; fi
cleanup() {{ rm -f "${{CONFIG}}.policy-new" "${{STATE}}.policy-new"; }}
rollback() {{
  cp -a "$CONFIG_BACKUP" "$CONFIG"
  if [ "$STATE_EXISTED" -eq 1 ]; then cp -a "$STATE_BACKUP" "$STATE"; else rm -f "$STATE"; fi
  systemctl restart "${{SERVICE}}.service" >/dev/null 2>&1 || true
}}
trap cleanup EXIT
printf '%s' {shlex.quote(doc_b64)} | base64 -d > "${{CONFIG}}.policy-new"
printf '%s' {shlex.quote(state_b64)} | base64 -d > "${{STATE}}.policy-new"
chmod 600 "${{CONFIG}}.policy-new" "${{STATE}}.policy-new"
"$BIN" check -c "${{CONFIG}}.policy-new"
mv "${{CONFIG}}.policy-new" "$CONFIG"
mv "${{STATE}}.policy-new" "$STATE"
chmod 600 "$CONFIG" "$STATE"
if ! systemctl restart "${{SERVICE}}.service"; then
  rollback
  echo policy_restart_failed_rolled_back >&2
  exit 63
fi
if ! systemctl is-active --quiet "${{SERVICE}}.service"; then
  rollback
  echo policy_service_not_active_rolled_back >&2
  exit 64
fi
printf '%s\n' "$CONFIG_BACKUP"
'''
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        detail = str(result.stderr or result.stdout or "policy_apply_failed").strip()
        raise HTTPException(
            status_code=502,
            detail={
                "message": "اعمال Policy ناموفق بود؛ تنظیمات قبلی بازیابی شد",
                "error": detail[-1800:],
            },
        )


async def _inventory_for_node(node, db: Session) -> dict[str, Any]:
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        state = await _read_state(conn)
        inventory = _inventory_from_document(doc)
        service = await conn.run(
            f"systemctl is-active {shlex.quote(SERVICE_NAME)}.service",
            check=False,
        )
        return {
            "ok": True,
            "schema": POLICY_SCHEMA,
            "node_id": node.id,
            "node_name": node.name,
            "service_active": service.exit_status == 0,
            "default_tag": inventory.get("default_tag"),
            "outbounds": inventory.get("outbounds", []),
            "protocols": _protocol_payload(
                doc=doc,
                state=state,
                default_tag=inventory.get("default_tag"),
            ),
            "capabilities": {
                "protocol_inventory_count": len(_PROTOCOLS),
                "native_protocol_policy": True,
                "classic_egress_adapter": False,
                "xray_egress_adapter": False,
                "modes": ["inherit", "direct", "outbound", "block"],
            },
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.get("/{node_id}")
async def get_policy_center(
    node_id: int,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    return await _inventory_for_node(node, db)


@router.patch("/{node_id}/{protocol}")
async def update_protocol_policy(
    node_id: int,
    protocol: str,
    payload: ProtocolPolicyIn,
    db: Session = Depends(get_db),
):
    key = str(protocol or "").strip().lower()
    key = _POLICY_ALIASES.get(key, key)
    spec = _PROTOCOL_BY_KEY.get(key)
    if not spec:
        raise HTTPException(status_code=404, detail="پروتکل در Policy Center شناخته نشد")
    if not spec.get("policy_supported"):
        reason = str(spec.get("reason") or "egress_adapter_required")
        raise HTTPException(
            status_code=409,
            detail={
                "message": "این پروتکل هنوز Egress Adapter واقعی ندارد",
                "reason": reason,
            },
        )

    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        inbound_tag = str(spec.get("inbound_tag") or "").strip()
        if inbound_tag not in _inbound_tags(doc):
            raise HTTPException(
                status_code=409,
                detail="این پروتکل روی Sing-box این نود نصب/فعال نیست",
            )

        outbound_tag = str(payload.outbound_tag or "").strip() or None
        if payload.mode == "outbound":
            if not outbound_tag:
                raise HTTPException(status_code=422, detail="Outbound مقصد را انتخاب کنید")
            if outbound_tag not in _outbound_tags(doc):
                raise HTTPException(status_code=422, detail="Outbound انتخاب‌شده روی این نود وجود ندارد")
            if outbound_tag == "direct":
                raise HTTPException(
                    status_code=422,
                    detail="برای مسیر مستقیم، حالت Direct را انتخاب کنید",
                )
        else:
            outbound_tag = None

        previous_state = await _read_state(conn)
        next_state = _clean_state(previous_state)
        policies = dict(next_state.get("policies") or {})
        policies[key] = {
            "mode": payload.mode,
            "outbound_tag": outbound_tag,
        }
        next_state["policies"] = policies

        next_doc, next_state = _apply_state_to_document(
            doc,
            next_state,
            [dict(item) for item in previous_state.get("generated_rules", []) if isinstance(item, dict)],
        )
        await _apply_documents(conn, doc=next_doc, state=next_state)
    finally:
        conn.close()
        await conn.wait_closed()

    return await _inventory_for_node(node, db)
