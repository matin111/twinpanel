"""Fail-closed Xray listener port allocation for a never-working TLS Exit.

A new Exit may use SSH on 8443 while the classic Xray installer also defaults
to 8443. Legacy installation leaves a valid config and cert but xray.service
FAILED with EADDRINUSE. Never steal SSH or sing-box ports or move a healthy
Xray service. Select a *complete* available base+TLS profile listener group,
and let the canonical provisioner store the resulting base in the DB.
"""
from __future__ import annotations

import json
import re
from typing import Any

_DEFAULT_XRAY_BASE = 8443
# Deterministic candidates avoid creating a new random public port at retry.
_FALLBACK_BASES = (12443, 13443, 14443, 15443, 16443, 17443, 18443, 19443)

_SAFE_PARTIAL_TAGS = frozenset({
    "vless-in", "api", "vless-xhttp-reality", "vless-ws-tls", "vless-tcp-tls",
    "vless-tcp-reality", "vless-tcp-reality-vision",
})

_READ_CONFIG = r"""python3 - <<'TP_XRAY_PORT_READ'
import json
from pathlib import Path

path=Path('/usr/local/etc/xray/config.json')
if not path.is_file():
    print(json.dumps({'safe':True,'clients':0,'configured':False}))
else:
    try:
        doc=json.loads(path.read_text(encoding='utf-8'))
        inbounds=doc.get('inbounds')
        if not isinstance(inbounds,list):
            raise ValueError('invalid inbounds')
        safe=True
        clients=0
        tags=[]
        base_port=0
        allowed={
            'vless-in','api','vless-xhttp-reality','vless-ws-tls',
            'vless-tcp-tls','vless-tcp-reality','vless-tcp-reality-vision',
        }
        for inbound in inbounds:
            if not isinstance(inbound,dict):
                safe=False
                continue
            tag=str(inbound.get('tag') or '')
            tags.append(tag)
            if tag=='vless-in':
                try:
                    base_port=int(inbound.get('port') or 0)
                except (ValueError,TypeError):
                    safe=False
            if tag not in allowed:
                safe=False
            if tag!='api' and inbound.get('protocol')!='vless':
                safe=False
            settings=inbound.get('settings') or {}
            if tag!='api':
                if not isinstance(settings,dict) or not isinstance(settings.get('clients'),list):
                    safe=False
                else:
                    clients+=len(settings['clients'])
        # Unknown custom routing or outbounds must not be overwritten.
        outbounds=doc.get('outbounds') or []
        if not isinstance(outbounds,list) or any(
            not isinstance(o,dict) or o.get('tag')!='direct'
            for o in outbounds
        ):
            safe=False
        state_path=Path('/usr/local/etc/xray/twinpanel-modern-state.json')
        try:
            state=json.loads(state_path.read_text(encoding='utf-8'))
            tls_domain=str(state.get('tls_domain') or '').strip().lower()
        except Exception:
            tls_domain=''
        print(json.dumps({'safe':safe,'clients':clients,'base_port':base_port,
                          'tls_domain':tls_domain,
                          'configured':True,'tags':tags},separators=(',',':')))
    except Exception:
        print(json.dumps({'safe':False,'clients':-1,'configured':True,
                          'reason':'invalid_or_unreadable_config'}))
TP_XRAY_PORT_READ"""


def _required_ports(base_port: int) -> frozenset[int]:
    """Use *live patched* profile offsets, never stale default values."""
    from .. import xray_modern_runtime as xr
    from ..xray_tcp_tls_v39 import _tcp_tls_target_port

    base = int(base_port)
    ports = frozenset((
        base,
        xr._target_port(base, xr.PROFILE_WS),
        xr._target_port(base, xr.PROFILE_XHTTP),
        _tcp_tls_target_port(base),
    ))
    if len(ports) != 4:
        raise RuntimeError("XRAY_BASE_PROFILE_PORT_OVERLAP")
    return ports


def _parse_tcp_listeners(text: str) -> dict[int, str]:
    occupied: dict[int, str] = {}
    for line in str(text).splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local_address = parts[3]
        port_text = local_address.rsplit(":", 1)[-1]
        if re.fullmatch(r"[0-9]+", port_text):
            occupied[int(port_text)] = line[:350]
    return occupied


def _is_tls_exit(node: Any) -> bool:
    kind = getattr(node, "node_type", "")
    role = str(getattr(kind, "value", kind) or "").lower()
    return bool(
        role == "exit"
        and str(getattr(node, "xray_domain", None) or "").strip()
    )


async def select_install_xray_base_port(conn, node: Any, requested_port: int) -> int:
    """Choose a safe TLS Xray port group before any node config write.

    The existing Xray base is authoritative for active or published nodes.
    Only a never-working TLS Exit, with no clients in a recognizable partial
    config, may move off a blocked default 8443 group. Explicit non-default
    base selections are never silently overridden.
    """
    requested = int(requested_port)
    if not _is_tls_exit(node):
        return requested

    from ..routers import provision

    if await provision.active(conn, "xray"):
        # An Exit might be deleted and re-added while its original Xray
        # service is *still* running under the same dedicated TLS identity.
        # Do not rewrite a healthy customer's instance with requested 8443.
        # Adopt the existing base only when there are ZERO remote clients,
        # all three live TLS inbounds agree with the new node domain, and
        # the previous state/config remain fully managed by TwinPanel.
        report_raw = await provision.cmd(
            conn, _READ_CONFIG, check=False, timeout=15,
        )
        try:
            report = json.loads(str(report_raw).strip().splitlines()[-1])
            installed_base = int(report.get("base_port") or 0)
        except (ValueError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError("XRAY_ACTIVE_CONFIG_AUDIT_FAILED") from exc
        if installed_base == requested:
            if (
                not bool(getattr(node, "enable_v2ray", False))
                and (
                    not report.get("safe")
                    or int(report.get("clients", -1)) != 0
                    or str(report.get("tls_domain") or "").lower()
                        != str(getattr(node, "xray_domain", "") or "").lower()
                )
            ):
                raise RuntimeError(
                    "XRAY_EXISTING_ACTIVE_CUSTOMER_DATA_OR_IDENTITY_STOP"
                )
            return requested
        if (
            requested != _DEFAULT_XRAY_BASE
            or bool(getattr(node, "enable_v2ray", False))
            or not report.get("safe")
            or int(report.get("clients", -1)) != 0
            or str(report.get("tls_domain") or "").lower()
                != str(getattr(node, "xray_domain", "") or "").lower()
            or not 1 <= installed_base <= 65535
        ):
            raise RuntimeError(
                "XRAY_EXISTING_ACTIVE_DIFFERENT_BASE_OR_IDENTITY_STOP"
            )
        from ..xray_modern_runtime import _three_tls_inbounds_live

        if not await _three_tls_inbounds_live(conn, installed_base, node):
            raise RuntimeError("XRAY_EXISTING_ACTIVE_THREE_INBOUNDS_NOT_READY")
        # Verified live adoption: no config, service or user-data mutations.
        return installed_base

    port_report = await provision.cmd(
        conn, "ss -H -lntp 2>/dev/null || echo XRAY_SS_UNAVAILABLE",
        check=False, timeout=12,
    )
    if "XRAY_SS_UNAVAILABLE" in str(port_report):
        raise RuntimeError("XRAY_LISTENER_PRECHECK_UNAVAILABLE")
    occupied = _parse_tcp_listeners(port_report)
    # The management API port is fixed independently of the listener base.
    # Never run a bootstrap that would steal it from another process.
    if 10085 in occupied:
        raise RuntimeError("XRAY_API_PORT_10085_ALREADY_IN_USE")
    wanted = _required_ports(requested)
    clashes = sorted(wanted.intersection(occupied))
    if not clashes:
        return requested

    # No hidden port moves on an already published/previously enabled Xray.
    if bool(getattr(node, "enable_v2ray", False)):
        raise RuntimeError(
            "XRAY_EXISTING_PUBLISHED_SERVICE_PORT_CONFLICT:"
            + ",".join(map(str, clashes))
        )
    if requested != _DEFAULT_XRAY_BASE:
        raise RuntimeError(
            "XRAY_CUSTOM_BASE_PORT_CONFLICT:"
            + ",".join(map(str, clashes))
        )

    report_raw = await provision.cmd(
        conn, _READ_CONFIG, check=False, timeout=15,
    )
    try:
        report = json.loads(str(report_raw).strip().splitlines()[-1])
    except (ValueError, IndexError, TypeError) as exc:
        raise RuntimeError("XRAY_PORT_REBASE_CONFIG_AUDIT_FAILED") from exc
    if not isinstance(report, dict) or report.get("safe") is not True:
        raise RuntimeError("XRAY_PORT_REBASE_UNRECOGNIZED_CONFIG_STOP")
    if int(report.get("clients", -1)) != 0:
        raise RuntimeError("XRAY_PORT_REBASE_CUSTOMER_IDENTITIES_STOP")

    # A detached Xray process can belong to an unmanaged instance even
    # when systemd reports failed. Never displace it automatically.
    if any("xray" in occupied[port].lower() for port in clashes):
        raise RuntimeError("XRAY_UNMANAGED_LISTENER_MANUAL_REVIEW")

    for candidate in _FALLBACK_BASES:
        required = _required_ports(candidate)
        if not required.intersection(occupied):
            return candidate

    raise RuntimeError("XRAY_NO_FREE_SAFE_TLS_PORT_GROUP")
