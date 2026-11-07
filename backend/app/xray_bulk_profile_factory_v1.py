"""Pure, idempotent local profile materialization for an existing Xray Exit.

Only reuse a *verified* modern profile template from the SAME node. Reality
public key/SNI, endpoint and transport are node-wide, while VLESS UUID and
display fragment are subscription-specific. This code performs no SSH or I/O.
"""
from __future__ import annotations

from copy import deepcopy
import re
import uuid
from urllib.parse import quote, unquote, urlsplit, urlunsplit

_VALID_PROFILE = frozenset({"xhttp_reality", "tcp_reality", "websocket_tls", "tcp_tls"})


def build_node_item_from_template(
    template: dict,
    *,
    node_id: int,
    template_uuid: str,
    client_uuid: str,
    account_label: str,
    required_profile_ids: set[str],
) -> dict:
    source_id = str(uuid.UUID(template_uuid))
    target_id = str(uuid.UUID(client_uuid))
    if not isinstance(template, dict) or int(template.get("node_id") or -1) != node_id:
        raise ValueError("Xray template must belong to selected node")
    if str(uuid.UUID(str(template.get("uuid")))) != source_id:
        raise ValueError("inconsistent Xray template UUID")
    if source_id == target_id:
        raise ValueError("template and target must be distinct")
    if not account_label or len(account_label) > 100:
        raise ValueError("invalid account label")
    if not required_profile_ids or not required_profile_ids.issubset(_VALID_PROFILE):
        raise ValueError("unsupported required Xray profiles")
    profiles = template.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("Xray template has no profiles")
    by_id = {}
    for p in profiles:
        if not isinstance(p, dict):
            raise ValueError("malformed Xray template profile")
        pid = str(p.get("id") or "").lower()
        if pid in by_id:
            raise ValueError("duplicate Xray template profile")
        by_id[pid] = p
    if not required_profile_ids.issubset(by_id):
        raise ValueError("Xray template lacks required profile")
    result = deepcopy(template)
    result["uuid"] = target_id
    generated = []
    for p in result["profiles"]:
        pid = str(p.get("id") or "").lower()
        if pid not in required_profile_ids:
            continue
        raw = str(p.get("uri") or "")
        uri = urlsplit(raw)
        if uri.scheme != "vless" or "@" not in uri.netloc:
            raise ValueError("invalid Xray template URI")
        user, authority = uri.netloc.split("@", 1)
        if user != source_id or not authority or not uri.hostname or not uri.port:
            raise ValueError("Xray template has unexpected identity or endpoint")
        if str(p.get("server") or "") != uri.hostname or int(p.get("port") or 0) != uri.port:
            raise ValueError("Xray template URI and endpoint disagree")
        # Query and Reality public settings must be byte-identical. Only
        # UUID and user-facing remark may differ across subscriptions.
        fragment = quote(f"{account_label}-{pid}", safe="")
        p["uri"] = urlunsplit(("vless", target_id + "@" + authority,
                               uri.path, uri.query, fragment))
        generated.append(p)
    result["profiles"] = generated
    if {str(p.get("id") or "").lower() for p in generated} != required_profile_ids:
        raise ValueError("Xray materialization produced incomplete profiles")
    primary = next((p for p in generated if p.get("recommended")), generated[0])
    result["uri"] = primary["uri"]
    result["server"] = primary["server"]
    result["server_ip"] = primary["server"]
    result["port"] = primary["port"]
    if any(source_id in str(p.get("uri")) for p in generated):
        raise ValueError("source UUID leaked into target")
    return result
