from __future__ import annotations

import ipaddress
import json
from typing import Any

from .database import SessionLocal
from .models import Node, NodeType
from . import naive_tls_lifecycle_v224 as naive_tls
from . import modern_protocol_tunnel_binding_v251 as tunnel_binding
from .routers import account_delivery


# TWINPANEL_NAIVE_TUNNEL_TLS_ORIGIN_V274
#
# NaiveProxy uses Chromium/Cronet. For this transport, tls.server_name is also
# the network origin Cronet resolves/dials; it is not only the certificate
# verification identity. V251 rewrites the transport address to the Iran
# ingress but historically left tls.server_name on the Exit identity, causing
# Cronet to dial Exit:<Iran-public-port> instead of the Iran ingress.
#
# Keep the fix deliberately Naive-only:
#   * managed-CA Naive delivery aligns tls.server_name with the Iran ingress;
#   * the managed leaf keeps the Exit SAN and additionally covers every current
#     non-retired Iran delivery identity so hostname verification stays strict;
#   * custom-certificate Naive and every other protocol keep existing behavior.

_RUNTIME_APPLIED = False
_ORIGINAL_SAFE_CERT_IDENTITY = naive_tls._safe_cert_identity
_ORIGINAL_REWRITE_SINGBOX_ITEM = tunnel_binding._rewrite_singbox_item


def _normalise_san(value: Any) -> str | None:
    host = str(value or "").strip().rstrip(".")
    if not host:
        return None

    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return f"DNS:{host.lower()}"

    return f"IP:{parsed.compressed}"


def _iran_delivery_sans() -> list[str]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Node)
            .filter(
                Node.node_type == NodeType.IRAN,
                Node.retired_at.is_(None),
            )
            .order_by(Node.id.asc())
            .all()
        )

        output: list[str] = []
        seen: set[str] = set()
        for node in rows:
            host = str(account_delivery._node_host(node) or "").strip()
            san = _normalise_san(host)
            if not san or san in seen:
                continue
            seen.add(san)
            output.append(san)
        return output
    finally:
        db.close()


def _safe_cert_identity_v274(node: Node) -> tuple[str, list[str]]:
    common_name, sans = _ORIGINAL_SAFE_CERT_IDENTITY(node)

    if node.node_type != NodeType.EXIT:
        return common_name, sans

    merged: list[str] = []
    seen: set[str] = set()
    for value in [*sans, *_iran_delivery_sans()]:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)

    return common_name, merged


def _align_naive_tls_identity(outbound: dict[str, Any], host: str) -> bool:
    if str(outbound.get("type") or "").strip().lower() != "naive":
        return False

    tls = outbound.get("tls")
    if not isinstance(tls, dict):
        return False

    updated_tls = dict(tls)
    updated_tls["server_name"] = str(host)
    outbound["tls"] = updated_tls
    return True


def _rewrite_singbox_item_v274(
    result: dict[str, Any],
    protocol: str,
    host: str,
    port: int,
) -> None:
    _ORIGINAL_REWRITE_SINGBOX_ITEM(result, protocol, host, port)

    if str(protocol or "").strip().lower() != "naive":
        return

    if str(result.get("tls_trust_model") or "").strip() != naive_tls.MANAGED_NAIVE_TRUST_MODEL:
        # Operator-owned certificates may not cover the Iran ingress identity.
        # Preserve historical custom-certificate behavior rather than weakening
        # verification or publishing a hostname the certificate cannot prove.
        return

    outbound = result.get("outbound")
    if isinstance(outbound, dict):
        _align_naive_tls_identity(outbound, host)

    raw = result.get("config")
    if not isinstance(raw, str) or not raw.strip():
        return

    try:
        doc = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return

    outbounds = doc.get("outbounds") if isinstance(doc, dict) else None
    if not isinstance(outbounds, list):
        return

    changed = False
    for candidate in outbounds:
        if isinstance(candidate, dict):
            changed = _align_naive_tls_identity(candidate, host) or changed

    if changed:
        result["config"] = json.dumps(doc, ensure_ascii=False, indent=2)


def apply_naive_tunnel_tls_origin_v274() -> None:
    global _RUNTIME_APPLIED

    if _RUNTIME_APPLIED:
        return

    # Existing managed lifecycle remains the authority for CA creation,
    # Chromium-compatible leaf lifetime, rollback and timer installation. Only
    # extend the SAN identity set it renders into the managed leaf/renew script.
    naive_tls._safe_cert_identity = _safe_cert_identity_v274

    # V251 remains the authority for Iran endpoint selection and public-port
    # mapping. Refine only Naive's managed TLS identity after V251 rewrites the
    # transport endpoint.
    tunnel_binding._rewrite_singbox_item = _rewrite_singbox_item_v274

    _RUNTIME_APPLIED = True
    print(
        "TWINPANEL_NAIVE_TUNNEL_TLS_ORIGIN_V274_ACTIVE "
        "dial_identity=iran-ingress managed_ca_sans=exit+iran custom_tls=unchanged",
        flush=True,
    )
