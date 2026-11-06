"""Pure connection projection for dynamically delivered non-V2Ray profiles.

Node-side values must be verified/applied on the server before enabling a
corresponding delivery override. Credential/identity fields are never copied
from node settings. No database writes, SSH, provisioning or restarts occur here.
"""
from __future__ import annotations

import copy
import ipaddress
import re
from typing import Any, Mapping

SUPPORTED_PROTOCOLS = frozenset({
    "hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell",
    "mieru", "trusttunnel", "sudoku", "wireguard", "amneziawg",
    "openvpn", "cisco", "l2tp",
})
# Only sing-box outbounds with these exact wire types can be projected as JSON.
SINGBOX_OUTBOUNDS = frozenset({
    "hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "mieru",
})

class ConnectionProjectionError(ValueError):
    """Invalid or incompatible central connection settings."""


def _valid_host(value: Any) -> str:
    host = str(value or "").strip()
    if not host or len(host) > 253 or any(c in host for c in "/\\?#@ \t\r\n"):
        raise ConnectionProjectionError("invalid connection host")
    # IPv6 bracket syntax is valid only for an actual IPv6 address.
    if host.startswith("[") or host.endswith("]"):
        if not (host.startswith("[") and host.endswith("]")):
            raise ConnectionProjectionError("invalid connection host")
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError as exc:
            raise ConnectionProjectionError("invalid connection host") from exc
        return host[1:-1]
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    # Neither a URL with :port nor arbitrary text is an allowed DNS host.
    if ":" in host or host.endswith("."):
        raise ConnectionProjectionError("invalid connection host")
    labels = host.split(".")
    if not all(
        len(part) <= 63 and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", part)
        for part in labels
    ):
        raise ConnectionProjectionError("invalid connection host")
    return host.lower()


def _valid_port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ConnectionProjectionError("invalid connection port") from exc
    if not 1 <= port <= 65535:
        raise ConnectionProjectionError("invalid connection port")
    return port


def project_singbox_item(
    protocol: str,
    item: Mapping[str, Any],
    connection: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a copy updated from *applied* node settings, never change auth.

    Only explicitly supplied keys are overridden. This intentionally does not
    guess tunnel domains, SNI, transport, wireguard keys or OpenVPN directives.
    JSON config and an existing outbound snapshot are updated consistently.
    """
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_OUTBOUNDS:
        raise ConnectionProjectionError("protocol requires a dedicated renderer")
    if not isinstance(item, Mapping) or not isinstance(connection, Mapping):
        raise ConnectionProjectionError("invalid projection input")
    updates: dict[str, Any] = {}
    if "host" in connection:
        updates["server"] = _valid_host(connection["host"])
    if "port" in connection:
        updates["server_port"] = _valid_port(connection["port"])
    if "sni" in connection:
        updates["sni"] = _valid_host(connection["sni"])

    def patch(outbound: dict[str, Any]) -> dict[str, Any]:
        if str(outbound.get("type") or "").lower() != protocol:
            return outbound
        if "server" in updates:
            outbound["server"] = updates["server"]
        if "server_port" in updates:
            outbound["server_port"] = updates["server_port"]
        if "sni" in updates:
            tls = outbound.get("tls")
            if not isinstance(tls, dict):
                raise ConnectionProjectionError("SNI override requires existing TLS")
            tls["server_name"] = updates["sni"]
        return outbound

    result = copy.deepcopy(dict(item))
    found = False
    outbound = result.get("outbound")
    if isinstance(outbound, dict) and str(outbound.get("type") or "").lower() == protocol:
        result["outbound"] = patch(outbound)
        found = True

    if isinstance(result.get("config"), str) and result["config"].strip():
        import json
        try:
            doc = json.loads(result["config"])
        except (TypeError, ValueError) as exc:
            raise ConnectionProjectionError("invalid sing-box JSON") from exc
        rows = doc.get("outbounds") if isinstance(doc, dict) else None
        if not isinstance(rows, list):
            raise ConnectionProjectionError("missing sing-box outbounds")
        for row in rows:
            if isinstance(row, dict) and str(row.get("type") or "").lower() == protocol:
                patch(row)
                found = True
        result["config"] = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    if not found:
        raise ConnectionProjectionError("matching outbound not found")
    # Existing URIs are derived artifacts; consumers must regenerate them from
    # the projected outbound rather than returning a now-stale saved URI.
    if updates:
        result.pop("uri", None)
    return result
