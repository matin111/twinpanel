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
from ..outbound_policy_native_adapters_v255 import NATIVE_POLICY_INBOUND_TAGS
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
POLICY_SCHEMA = 2

XRAY_CONFIG_PATH = "/usr/local/etc/xray/config.json"
XRAY_SERVICE_NAME = "xray"
XRAY_BIN = "/usr/local/bin/xray"
XRAY_INBOUND_TAG = "vless-in"
XRAY_BRIDGE_INBOUND_TAG = "twinpanel-xray-policy-bridge-in"
XRAY_BRIDGE_OUTBOUND_TAG = "twinpanel-xray-policy-bridge"
XRAY_BLOCK_OUTBOUND_TAG = "twinpanel-xray-policy-block"
XRAY_BRIDGE_PORT = 19081

KERNEL_TUN_TAG = "twinpanel-kernel-policy-in"
KERNEL_TUN_NAME = "tp-policy0"
KERNEL_TUN_ADDRESS = "198.18.255.1/30"
KERNEL_TUN_MTU = 1400

KERNEL_POLICY_SPECS: dict[str, dict[str, Any]] = {
    "cisco": {"source_cidr": "10.91.0.0/24", "table": 10910, "priority": 10910},
    "openvpn": {"source_cidr": "10.92.0.0/24", "table": 10920, "priority": 10920},
    "wireguard": {"source_cidr": "10.93.0.0/24", "table": 10930, "priority": 10930},
    "l2tp": {"source_cidr": "10.94.0.0/24", "table": 10940, "priority": 10940},
}

_NATIVE_POLICY_ORDER: tuple[str, ...] = (
    "hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell",
)
_KERNEL_POLICY_ORDER: tuple[str, ...] = tuple(KERNEL_POLICY_SPECS)
_XRAY_POLICY_ORDER: tuple[str, ...] = ("v2ray",)
_POLICY_ALIASES = {"xray": "v2ray"}
_supported_order = set(_NATIVE_POLICY_ORDER) | set(_KERNEL_POLICY_ORDER) | set(_XRAY_POLICY_ORDER)
_PROTOCOL_ORDER: tuple[str, ...] = (
    *_NATIVE_POLICY_ORDER,
    *_KERNEL_POLICY_ORDER,
    *_XRAY_POLICY_ORDER,
    *(key for key in ALL_PROTOCOL_KEYS if key not in _supported_order),
)

router = APIRouter(
    prefix="/v1/settings/vpn/outbound-policy",
    tags=["outbound-policy-center-v2"],
    dependencies=[Depends(require_admin)],
)
PolicyMode = Literal["inherit", "direct", "outbound", "block"]


class ProtocolPolicyIn(BaseModel):
    mode: PolicyMode
    outbound_tag: str | None = Field(default=None, min_length=1, max_length=63)


def _protocol_spec(key: str) -> dict[str, Any]:
    if key in NATIVE_POLICY_INBOUND_TAGS:
        definition = PROTOCOL_CATALOG.get(key, {})
        return {
            "key": key,
            "title": str(definition.get("title") or PROTOCOL_TITLES[key]),
            "family": "modern",
            "plane": "singbox",
            "core": str(definition.get("core") or "sing-box"),
            "runtime_status": str(definition.get("runtime_status") or "ready"),
            "inbound_tag": NATIVE_POLICY_INBOUND_TAGS[key],
            "policy_supported": True,
            "reason": None,
            "adapter_kind": "singbox-native",
        }
    if key in KERNEL_POLICY_SPECS:
        definition = CLASSIC_PROTOCOL_REGISTRY[key]
        return {
            "key": key,
            "title": str(definition.get("title") or PROTOCOL_TITLES[key]),
            "family": "classic",
            "plane": "kernel",
            "core": str(definition.get("core") or PROTOCOL_TITLES[key]),
            "runtime_status": str(definition.get("runtime_status") or "ready"),
            "inbound_tag": KERNEL_TUN_TAG,
            "policy_supported": True,
            "reason": None,
            "adapter_kind": "kernel-tun",
            "source_cidr": KERNEL_POLICY_SPECS[key]["source_cidr"],
        }
    if key == "v2ray":
        definition = CLASSIC_PROTOCOL_REGISTRY[key]
        return {
            "key": key,
            "title": str(definition.get("title") or PROTOCOL_TITLES[key]),
            "family": "classic",
            "plane": "xray",
            "core": str(definition.get("core") or "Xray"),
            "runtime_status": str(definition.get("runtime_status") or "ready"),
            "inbound_tag": XRAY_INBOUND_TAG,
            "policy_supported": True,
            "reason": None,
            "adapter_kind": "xray-bridge",
        }
    definition = PROTOCOL_CATALOG.get(key, {})
    runtime_status = str(definition.get("runtime_status") or "unknown")
    reason = (
        "runtime_core_pending"
        if runtime_status in {"adapter_pending", "experimental_pending"}
        else "protocol_egress_adapter_required"
    )
    return {
        "key": key,
        "title": str(definition.get("title") or PROTOCOL_TITLES[key]),
        "family": "modern",
        "plane": "standalone",
        "core": str(definition.get("core") or "standalone"),
        "runtime_status": runtime_status,
        "inbound_tag": None,
        "policy_supported": False,
        "reason": reason,
        "adapter_kind": None,
    }


_PROTOCOLS: tuple[dict[str, Any], ...] = tuple(_protocol_spec(key) for key in _PROTOCOL_ORDER)
_PROTOCOL_BY_KEY = {str(item["key"]): item for item in _PROTOCOLS}


def _empty_state() -> dict[str, Any]:
    return {
        "schema": POLICY_SCHEMA,
        "policies": {},
        "generated_rules": [],
        "xray_generated_rules": [],
        "xray_generated_outbounds": [],
    }


def _clean_state(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_state()
    policies = raw.get("policies") if isinstance(raw.get("policies"), dict) else {}
    generated = raw.get("generated_rules") if isinstance(raw.get("generated_rules"), list) else []
    xray_rules = raw.get("xray_generated_rules") if isinstance(raw.get("xray_generated_rules"), list) else []
    xray_outbounds = raw.get("xray_generated_outbounds") if isinstance(raw.get("xray_generated_outbounds"), list) else []
    return {
        "schema": POLICY_SCHEMA,
        "policies": {str(k): dict(v) for k, v in policies.items() if isinstance(v, dict)},
        "generated_rules": [dict(x) for x in generated if isinstance(x, dict)],
        "xray_generated_rules": [dict(x) for x in xray_rules if isinstance(x, dict)],
        "xray_generated_outbounds": [dict(x) for x in xray_outbounds if isinstance(x, dict)],
    }


async def _read_state(conn) -> dict[str, Any]:
    result = await conn.run(f"cat {shlex.quote(POLICY_STATE_PATH)}", check=False)
    if result.exit_status != 0 or not str(result.stdout or "").strip():
        return _empty_state()
    try:
        return _clean_state(json.loads(result.stdout))
    except Exception:
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
    mode = str(policy.get("mode") or "inherit").strip().lower()
    if mode == "inherit":
        return None

    if protocol == "v2ray":
        if mode != "outbound":
            return None
        outbound_tag = str(policy.get("outbound_tag") or "").strip()
        if not outbound_tag:
            raise ValueError("outbound_tag_required:v2ray")
        return {
            "inbound": [XRAY_BRIDGE_INBOUND_TAG],
            "action": "route",
            "outbound": outbound_tag,
        }

    if protocol in KERNEL_POLICY_SPECS:
        match: dict[str, Any] = {
            "source_ip_cidr": [str(KERNEL_POLICY_SPECS[protocol]["source_cidr"])]
        }
    else:
        inbound_tag = str(spec.get("inbound_tag") or "").strip()
        if not inbound_tag:
            return None
        match = {"inbound": [inbound_tag]}

    if mode == "block":
        return {**match, "action": "reject", "method": "default"}
    if mode == "direct":
        return {**match, "action": "route", "outbound": "direct"}
    if mode == "outbound":
        outbound_tag = str(policy.get("outbound_tag") or "").strip()
        if not outbound_tag:
            raise ValueError(f"outbound_tag_required:{protocol}")
        return {**match, "action": "route", "outbound": outbound_tag}
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


def _strip_previous_generated_rules(rules: list[Any], previous: list[dict[str, Any]]) -> list[Any]:
    remaining: list[Any] = []
    pending = [dict(item) for item in previous]
    for item in rules:
        if isinstance(item, dict):
            index = next((i for i, old in enumerate(pending) if old == item), None)
            if index is not None:
                pending.pop(index)
                continue
        remaining.append(item)
    return remaining


def _managed_tun_required(state: dict[str, Any]) -> bool:
    return any(_policy_record(state, key)["mode"] != "inherit" for key in KERNEL_POLICY_SPECS)


def _xray_bridge_required(state: dict[str, Any]) -> bool:
    return _policy_record(state, "v2ray")["mode"] == "outbound"


def _reconcile_managed_policy_inbounds(doc: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    fresh = json.loads(json.dumps(doc))
    inbounds = fresh.get("inbounds") if isinstance(fresh.get("inbounds"), list) else []
    managed_tags = {KERNEL_TUN_TAG, XRAY_BRIDGE_INBOUND_TAG}
    retained = [
        item for item in inbounds
        if not (isinstance(item, dict) and str(item.get("tag") or "") in managed_tags)
    ]
    if _managed_tun_required(state):
        retained.append({
            "type": "tun",
            "tag": KERNEL_TUN_TAG,
            "interface_name": KERNEL_TUN_NAME,
            "address": [KERNEL_TUN_ADDRESS],
            "mtu": KERNEL_TUN_MTU,
            "auto_route": False,
        })
    if _xray_bridge_required(state):
        retained.append({
            "type": "socks",
            "tag": XRAY_BRIDGE_INBOUND_TAG,
            "listen": "127.0.0.1",
            "listen_port": XRAY_BRIDGE_PORT,
        })
    fresh["inbounds"] = retained
    return fresh


def _apply_state_to_document(
    doc: dict[str, Any],
    state: dict[str, Any],
    previous_generated: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    fresh_doc = _reconcile_managed_policy_inbounds(doc, state)
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


def _xray_generated(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mode = str(policy.get("mode") or "inherit").strip().lower()
    if mode == "inherit":
        return [], []
    if mode == "direct":
        return [{
            "type": "field",
            "inboundTag": [XRAY_INBOUND_TAG],
            "outboundTag": "direct",
        }], []
    if mode == "block":
        return [{
            "type": "field",
            "inboundTag": [XRAY_INBOUND_TAG],
            "outboundTag": XRAY_BLOCK_OUTBOUND_TAG,
        }], [{
            "protocol": "blackhole",
            "tag": XRAY_BLOCK_OUTBOUND_TAG,
            "settings": {},
        }]
    if mode == "outbound":
        return [{
            "type": "field",
            "inboundTag": [XRAY_INBOUND_TAG],
            "outboundTag": XRAY_BRIDGE_OUTBOUND_TAG,
        }], [{
            "protocol": "socks",
            "tag": XRAY_BRIDGE_OUTBOUND_TAG,
            "settings": {"address": "127.0.0.1", "port": XRAY_BRIDGE_PORT},
        }]
    raise ValueError(f"unsupported_xray_policy_mode:{mode}")


def _apply_xray_policy_to_document(
    doc: dict[str, Any],
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    fresh_doc = json.loads(json.dumps(doc))
    fresh_state = _clean_state(state)
    previous_rules = [
        dict(x) for x in fresh_state.get("xray_generated_rules", []) if isinstance(x, dict)
    ]
    previous_outbounds = [
        dict(x) for x in fresh_state.get("xray_generated_outbounds", []) if isinstance(x, dict)
    ]
    routing = fresh_doc.get("routing") if isinstance(fresh_doc.get("routing"), dict) else {}
    existing_rules = routing.get("rules") if isinstance(routing.get("rules"), list) else []
    existing_outbounds = fresh_doc.get("outbounds") if isinstance(fresh_doc.get("outbounds"), list) else []
    retained_rules = _strip_previous_generated_rules(existing_rules, previous_rules)
    retained_outbounds = _strip_previous_generated_rules(existing_outbounds, previous_outbounds)
    generated_rules, generated_outbounds = _xray_generated(_policy_record(fresh_state, "v2ray"))

    mode = _policy_record(fresh_state, "v2ray")["mode"]
    if mode == "direct" and not any(
        isinstance(item, dict) and item.get("tag") == "direct" for item in retained_outbounds
    ):
        raise ValueError("xray_direct_outbound_missing")

    routing["rules"] = generated_rules + retained_rules
    fresh_doc["routing"] = routing
    fresh_doc["outbounds"] = generated_outbounds + retained_outbounds
    fresh_state["xray_generated_rules"] = generated_rules
    fresh_state["xray_generated_outbounds"] = generated_outbounds
    return fresh_doc, fresh_state


async def _read_xray_document(conn) -> dict[str, Any]:
    result = await conn.run(f"cat {shlex.quote(XRAY_CONFIG_PATH)}", check=False)
    if result.exit_status != 0:
        raise HTTPException(status_code=409, detail="Xray config روی این نود پیدا نشد")
    try:
        doc = json.loads(result.stdout or "{}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Xray config روی نود JSON معتبر نیست") from exc
    if not isinstance(doc, dict):
        raise HTTPException(status_code=502, detail="Xray config معتبر نیست")
    return doc


def _kernel_reconcile_script(state: dict[str, Any]) -> str:
    active = [
        (key, spec)
        for key, spec in KERNEL_POLICY_SPECS.items()
        if _policy_record(state, key)["mode"] != "inherit"
    ]
    lines = ["set -eu"]
    for spec in KERNEL_POLICY_SPECS.values():
        priority = int(spec["priority"])
        table = int(spec["table"])
        lines.extend([
            f"while ip -4 rule del priority {priority} 2>/dev/null; do :; done",
            f"ip -4 route flush table {table} 2>/dev/null || true",
        ])
    if active:
        lines.append(f"ip link show {shlex.quote(KERNEL_TUN_NAME)} >/dev/null 2>&1")
    for _key, spec in active:
        table = int(spec["table"])
        priority = int(spec["priority"])
        source_cidr = shlex.quote(str(spec["source_cidr"]))
        lines.extend([
            f"ip -4 route replace throw 10.0.0.0/8 table {table}",
            f"ip -4 route replace throw 172.16.0.0/12 table {table}",
            f"ip -4 route replace throw 192.168.0.0/16 table {table}",
            f"ip -4 route replace throw 169.254.0.0/16 table {table}",
            f"ip -4 route replace default dev {shlex.quote(KERNEL_TUN_NAME)} table {table}",
            f"ip -4 rule add priority {priority} from {source_cidr} lookup {table}",
        ])
    return "\n".join(lines) + "\n"


def _effective_outbound(
    *,
    protocol: str,
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
    spec = _PROTOCOL_BY_KEY.get(protocol) or {}
    if spec.get("adapter_kind") in {"kernel-tun", "xray-bridge"}:
        return "direct"
    return default_tag or "direct"


async def _runtime_installation_map(conn, doc: dict[str, Any]) -> dict[str, bool]:
    tags = _inbound_tags(doc)
    result = {key: tag in tags for key, tag in NATIVE_POLICY_INBOUND_TAGS.items()}
    probes = {
        "cisco": "systemctl is-active --quiet ocserv && test -s /etc/ocserv/ocserv.conf",
        "openvpn": "systemctl is-active --quiet openvpn-server@twinpanel && test -s /etc/openvpn/server/twinpanel.conf",
        "wireguard": "wg show wg-access0 >/dev/null 2>&1 && test -s /etc/wireguard/wg-access0.conf",
        "l2tp": "(systemctl is-active --quiet strongswan-starter || systemctl is-active --quiet strongswan) && systemctl is-active --quiet xl2tpd && test -s /etc/xl2tpd/xl2tpd.conf",
        "v2ray": "systemctl is-active --quiet xray && test -s /usr/local/etc/xray/config.json && python3 -c " + shlex.quote(
            "import json,sys; d=json.load(open('/usr/local/etc/xray/config.json',encoding='utf-8')); "
            "sys.exit(0 if any(isinstance(x,dict) and x.get('tag')=='vless-in' for x in d.get('inbounds',[])) else 1)"
        ),
    }
    for key, command in probes.items():
        check = await conn.run(command, check=False)
        result[key] = check.exit_status == 0
    return result


def _protocol_payload(
    *,
    doc: dict[str, Any],
    state: dict[str, Any],
    default_tag: str | None,
    installed_map: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    installed_map = installed_map or {}
    rows: list[dict[str, Any]] = []
    for spec in _PROTOCOLS:
        key = str(spec["key"])
        supported = bool(spec.get("policy_supported"))
        policy = _policy_record(state, key)
        rows.append({
            "key": key,
            "title": spec["title"],
            "family": spec.get("family"),
            "plane": spec["plane"],
            "core": spec.get("core"),
            "runtime_status": spec.get("runtime_status"),
            "inbound_tag": spec.get("inbound_tag"),
            "policy_supported": supported,
            "installed": bool(installed_map.get(key, False)) if supported else None,
            "reason": spec.get("reason"),
            "adapter_kind": spec.get("adapter_kind"),
            "mode": policy["mode"],
            "outbound_tag": policy["outbound_tag"],
            "effective_outbound": _effective_outbound(
                protocol=key, policy=policy, default_tag=default_tag
            ),
        })
    return rows


def _encode_json(doc: dict[str, Any]) -> str:
    return base64.b64encode(
        json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    ).decode("ascii")


def _kernel_script_b64(state: dict[str, Any]) -> str:
    return base64.b64encode(_kernel_reconcile_script(state).encode()).decode("ascii")


async def _apply_transaction(
    conn,
    *,
    doc: dict[str, Any],
    state: dict[str, Any],
    previous_state: dict[str, Any],
    xray_doc: dict[str, Any] | None,
) -> None:
    doc_b64 = _encode_json(doc)
    state_b64 = _encode_json(state)
    next_kernel_b64 = _kernel_script_b64(state)
    previous_kernel_b64 = _kernel_script_b64(previous_state)
    clear_kernel_b64 = _kernel_script_b64(_empty_state())
    xray_enabled = xray_doc is not None
    xray_b64 = _encode_json(xray_doc) if xray_doc is not None else ""

    command = f'''set -eu
CONFIG={shlex.quote(CONFIG_PATH)}
STATE={shlex.quote(POLICY_STATE_PATH)}
SERVICE={shlex.quote(SERVICE_NAME)}
BIN=/usr/local/bin/twinpanel-sing-box
XRAY_CONFIG={shlex.quote(XRAY_CONFIG_PATH)}
XRAY_SERVICE={shlex.quote(XRAY_SERVICE_NAME)}
XRAY_BIN={shlex.quote(XRAY_BIN)}
XRAY_ENABLED={"1" if xray_enabled else "0"}

if [ ! -x "$BIN" ]; then BIN="$(command -v sing-box || true)"; fi
[ -n "$BIN" ] || {{ echo singbox_binary_missing >&2; exit 61; }}
[ -s "$CONFIG" ] || {{ echo singbox_config_missing >&2; exit 62; }}
mkdir -p "$(dirname "$STATE")"

STAMP="$(date +%Y%m%d-%H%M%S)-$$"
CONFIG_BACKUP="${{CONFIG}}.policy-backup-${{STAMP}}"
STATE_BACKUP="${{STATE}}.policy-backup-${{STAMP}}"
XRAY_BACKUP="${{XRAY_CONFIG}}.policy-backup-${{STAMP}}"
STATE_EXISTED=0
XRAY_EXISTED=0
cp -a "$CONFIG" "$CONFIG_BACKUP"
if [ -e "$STATE" ]; then cp -a "$STATE" "$STATE_BACKUP"; STATE_EXISTED=1; fi
if [ "$XRAY_ENABLED" -eq 1 ]; then
  [ -x "$XRAY_BIN" ] || {{ echo xray_binary_missing >&2; exit 65; }}
  [ -s "$XRAY_CONFIG" ] || {{ echo xray_config_missing >&2; exit 66; }}
  cp -a "$XRAY_CONFIG" "$XRAY_BACKUP"
  XRAY_EXISTED=1
fi

cleanup() {{
  rm -f "${{CONFIG}}.policy-new" "${{STATE}}.policy-new" "${{XRAY_CONFIG}}.policy-new"
}}
restore_kernel() {{
  printf '%s' {shlex.quote(previous_kernel_b64)} | base64 -d | bash >/dev/null 2>&1 || true
}}
rollback() {{
  printf '%s' {shlex.quote(clear_kernel_b64)} | base64 -d | bash >/dev/null 2>&1 || true
  cp -a "$CONFIG_BACKUP" "$CONFIG"
  if [ "$STATE_EXISTED" -eq 1 ]; then cp -a "$STATE_BACKUP" "$STATE"; else rm -f "$STATE"; fi
  if [ "$XRAY_ENABLED" -eq 1 ] && [ "$XRAY_EXISTED" -eq 1 ]; then cp -a "$XRAY_BACKUP" "$XRAY_CONFIG"; fi
  systemctl restart "${{SERVICE}}.service" >/dev/null 2>&1 || true
  if [ "$XRAY_ENABLED" -eq 1 ]; then systemctl restart "${{XRAY_SERVICE}}.service" >/dev/null 2>&1 || true; fi
  restore_kernel
}}
trap cleanup EXIT

printf '%s' {shlex.quote(doc_b64)} | base64 -d > "${{CONFIG}}.policy-new"
printf '%s' {shlex.quote(state_b64)} | base64 -d > "${{STATE}}.policy-new"
chmod 600 "${{CONFIG}}.policy-new" "${{STATE}}.policy-new"
"$BIN" check -c "${{CONFIG}}.policy-new"

if [ "$XRAY_ENABLED" -eq 1 ]; then
  printf '%s' {shlex.quote(xray_b64)} | base64 -d > "${{XRAY_CONFIG}}.policy-new"
  chmod 600 "${{XRAY_CONFIG}}.policy-new"
  "$XRAY_BIN" run -test -config "${{XRAY_CONFIG}}.policy-new"
fi

printf '%s' {shlex.quote(clear_kernel_b64)} | base64 -d | bash
mv "${{CONFIG}}.policy-new" "$CONFIG"
mv "${{STATE}}.policy-new" "$STATE"
chmod 600 "$CONFIG" "$STATE"
if [ "$XRAY_ENABLED" -eq 1 ]; then
  mv "${{XRAY_CONFIG}}.policy-new" "$XRAY_CONFIG"
  chmod 600 "$XRAY_CONFIG"
fi

if ! systemctl restart "${{SERVICE}}.service"; then rollback; echo policy_singbox_restart_failed_rolled_back >&2; exit 67; fi
if ! systemctl is-active --quiet "${{SERVICE}}.service"; then rollback; echo policy_singbox_not_active_rolled_back >&2; exit 68; fi

if [ "$XRAY_ENABLED" -eq 1 ]; then
  if ! systemctl restart "${{XRAY_SERVICE}}.service"; then rollback; echo policy_xray_restart_failed_rolled_back >&2; exit 69; fi
  if ! systemctl is-active --quiet "${{XRAY_SERVICE}}.service"; then rollback; echo policy_xray_not_active_rolled_back >&2; exit 70; fi
fi

if ! printf '%s' {shlex.quote(next_kernel_b64)} | base64 -d | bash; then
  rollback
  echo policy_kernel_route_failed_rolled_back >&2
  exit 71
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
        installed_map = await _runtime_installation_map(conn, doc)
        service = await conn.run(
            f"systemctl is-active {shlex.quote(SERVICE_NAME)}.service", check=False
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
                installed_map=installed_map,
            ),
            "capabilities": {
                "protocol_inventory_count": len(_PROTOCOLS),
                "route_ready_count": sum(1 for item in _PROTOCOLS if item.get("policy_supported")),
                "native_protocol_policy": True,
                "classic_egress_adapter": True,
                "xray_egress_adapter": True,
                "standalone_runtime_pending": [
                    key for key in ALL_PROTOCOL_KEYS
                    if not _PROTOCOL_BY_KEY[key].get("policy_supported")
                ],
                "modes": ["inherit", "direct", "outbound", "block"],
            },
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.get("/{node_id}")
async def get_policy_center(node_id: int, db: Session = Depends(get_db)):
    return await _inventory_for_node(_node(db, node_id), db)


@router.patch("/{node_id}/{protocol}")
async def update_protocol_policy(
    node_id: int,
    protocol: str,
    payload: ProtocolPolicyIn,
    db: Session = Depends(get_db),
):
    raw_key = str(protocol or "").strip().lower()
    key = _POLICY_ALIASES.get(raw_key, raw_key)
    spec = _PROTOCOL_BY_KEY.get(key)
    if not spec:
        raise HTTPException(status_code=404, detail="پروتکل در Policy Center شناخته نشد")
    if not spec.get("policy_supported"):
        reason = str(spec.get("reason") or "egress_adapter_required")
        message = (
            "Runtime اصلی این پروتکل هنوز Production-Ready نیست"
            if reason == "runtime_core_pending"
            else "این پروتکل هنوز Egress Adapter واقعی ندارد"
        )
        raise HTTPException(status_code=409, detail={"message": message, "reason": reason})

    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        installed_map = await _runtime_installation_map(conn, doc)
        if not installed_map.get(key, False):
            raise HTTPException(status_code=409, detail="Runtime این پروتکل روی نود نصب/فعال نیست")

        outbound_tag = str(payload.outbound_tag or "").strip() or None
        if payload.mode == "outbound":
            if not outbound_tag:
                raise HTTPException(status_code=422, detail="Outbound مقصد را انتخاب کنید")
            if outbound_tag not in _outbound_tags(doc):
                raise HTTPException(status_code=422, detail="Outbound انتخاب‌شده روی این نود وجود ندارد")
            if outbound_tag == "direct":
                raise HTTPException(status_code=422, detail="برای مسیر مستقیم، حالت Direct را انتخاب کنید")
        else:
            outbound_tag = None

        previous_state = await _read_state(conn)
        next_state = _clean_state(previous_state)
        policies = dict(next_state.get("policies") or {})
        policies[key] = {"mode": payload.mode, "outbound_tag": outbound_tag}
        next_state["policies"] = policies

        next_doc, next_state = _apply_state_to_document(
            doc,
            next_state,
            [dict(x) for x in previous_state.get("generated_rules", []) if isinstance(x, dict)],
        )

        xray_doc: dict[str, Any] | None = None
        if key == "v2ray":
            xray_doc, next_state = _apply_xray_policy_to_document(
                await _read_xray_document(conn), next_state
            )

        await _apply_transaction(
            conn,
            doc=next_doc,
            state=next_state,
            previous_state=previous_state,
            xray_doc=xray_doc,
        )
    finally:
        conn.close()
        await conn.wait_closed()

    return await _inventory_for_node(node, db)
