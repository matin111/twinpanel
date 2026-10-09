from __future__ import annotations
from ..services.public_urls import subscription_base_url, shop_base_url

import base64
import hashlib
import hmac
import html
import io
import json
import re
import secrets
import shlex
import uuid
from datetime import datetime, timedelta
from typing import Any

import qrcode
import qrcode.image.svg

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Body, APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_admin, get_current_user
from ..quota_models import QuotaUsageEvent
from ..subscription_enforcement import queue_subscription_enforcement
from ..models import (
    Node,
    NodeType,
    NodeProtocolConfig,
    Tunnel,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    User,
)
from .provision import cmd, ssh_connect_saved
from ..mother_access import get_or_create_l2tp_psk
from ..protocol_identity import (
    get_or_create_openvpn_client_identity,
    is_openvpn_central_pki_enabled,
)

router = APIRouter(prefix="/v1/subscriptions", tags=["account-delivery"], dependencies=[Depends(require_admin)])

public_router = APIRouter(
    prefix="/v1/connect",
    tags=["public-connection"]
)
public_router = APIRouter(prefix="/v1/connect", tags=["public-connection"])


# TWINPANEL_CUSTOMER_CONNECTION_INFO_V1
customer_router = APIRouter(
    prefix="/v1/customer/subscriptions",
    tags=["customer-account-delivery"],
)


DEFAULT_PORTS = {"cisco": 4443, "openvpn": 1194, "wireguard": 51820, "l2tp": 1701, "v2ray": 8443}
DOWNLOADS = {
    "windows": [
        {"name": "OpenVPN Connect", "url": "https://openvpn.net/client/"},
        {"name": "WireGuard", "url": "https://www.wireguard.com/install/"},
        {"name": "Cisco Secure Client", "url": "https://www.cisco.com/c/en/us/support/docs/security/umbrella/224780-download-cisco-secure-client.html"},
        {"name": "v2rayN", "url": "https://github.com/2dust/v2rayN/releases"},
    ],
    "macos": [
        {"name": "OpenVPN Connect", "url": "https://openvpn.net/client/"},
        {"name": "WireGuard", "url": "https://www.wireguard.com/install/"},
        {"name": "Cisco Secure Client", "url": "https://www.cisco.com/c/en/us/support/docs/security/umbrella/224780-download-cisco-secure-client.html"},
        {"name": "Hiddify", "url": "https://github.com/hiddify/hiddify-app/releases"},
    ],
    "android": [
        {"name": "OpenVPN Connect", "url": "https://openvpn.net/client/"},
        {"name": "WireGuard", "url": "https://www.wireguard.com/install/"},
        {"name": "Hiddify", "url": "https://github.com/hiddify/hiddify-app/releases"},
    ],
    "ios": [
        {"name": "OpenVPN Connect", "url": "https://openvpn.net/client/"},
        {"name": "WireGuard", "url": "https://www.wireguard.com/install/"},
        {"name": "Hiddify", "url": "https://github.com/hiddify/hiddify-app/releases"},
    ],
    "linux": [
        {"name": "OpenVPN", "url": "https://openvpn.net/client/"},
        {"name": "WireGuard", "url": "https://www.wireguard.com/install/"},
        {"name": "v2rayN", "url": "https://github.com/2dust/v2rayN/releases"},
        {"name": "Hiddify", "url": "https://github.com/hiddify/hiddify-app/releases"},
    ],
}



def _simple_secret(prefix: str = "Mv", count: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return prefix + "".join(secrets.choice(alphabet) for _ in range(count))


def _numeric_secret(count: int = 8) -> str:
    # Easy to type on phones while avoiding a leading zero.
    return secrets.choice("123456789") + "".join(secrets.choice("0123456789") for _ in range(count - 1))


# TWINPANEL_STABLE_SHARE_TOKEN_V2
def _share_token(sub: Subscription) -> str:
    """
    Preferred public subscription token.

    Existing persistent share_code always wins.
    The signed v2 token is only a fallback for legacy rows
    which do not yet have share_code.
    """
    share_code = str(
        getattr(sub, "share_code", None)
        or ""
    ).strip()

    if share_code:
        return share_code

    payload = f"v2:{sub.id}"

    sig = hmac.new(
        settings.app_secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]

    return base64.urlsafe_b64encode(
        f"v2:{sub.id}:{sig}".encode()
    ).decode().rstrip("=")


def _check_public_subscription(
    sub: Subscription,
) -> Subscription:
    status_value = getattr(
        sub.status,
        "value",
        str(sub.status),
    )

    # وضعیت اشتراک فقط برای جلوگیری از تحویل کانفیگ بررسی می‌شود.
    # صفحه عمومی باید باز شود تا کاربر پیام غیرفعال بودن را ببیند.
    if status_value != "active":
        return sub

    if (
        sub.expires_at
        and sub.expires_at <= datetime.utcnow()
    ):
        raise HTTPException(
            status_code=403,
            detail="اشتراک منقضی شده است",
        )

    return sub


def _subscription_from_share_token(
    token: str,
    db: Session,
) -> Subscription:
    """
    Supports all generations:

    1. Persistent short share_code
    2. v2 stable signed token:
       v2:id:signature
    3. Legacy complete token:
       id:expiry:signature
    4. Legacy broken token previously generated by this app:
       id:signature
       Signature was calculated from id:current_expiry.
    """
    token = str(token or "").strip()

    if not token:
        raise HTTPException(
            status_code=404,
            detail="لینک اتصال معتبر نیست",
        )

    # ------------------------------------------------------
    # Persistent short share code
    # ------------------------------------------------------

    sub = (
        db.query(Subscription)
        .filter(
            Subscription.share_code == token
        )
        .first()
    )

    if sub:
        return _check_public_subscription(sub)

    # ------------------------------------------------------
    # Signed long-token compatibility
    # ------------------------------------------------------

    try:
        padded = token + "=" * (-len(token) % 4)

        decoded = base64.urlsafe_b64decode(
            padded.encode()
        ).decode()

        parts = decoded.split(":")

        # --------------------------------------------------
        # V2 stable token
        # v2:id:sig
        # --------------------------------------------------

        if (
            len(parts) == 3
            and parts[0] == "v2"
        ):
            _, sid_text, supplied = parts

            if (
                not sid_text.isdigit()
                or len(supplied) != 32
            ):
                raise ValueError("v2-format")

            payload = f"v2:{sid_text}"

            expected = hmac.new(
                settings.app_secret_key.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()[:32]

            if not hmac.compare_digest(
                supplied,
                expected,
            ):
                raise ValueError("v2-signature")

            sub = db.get(
                Subscription,
                int(sid_text),
            )

            if not sub:
                raise ValueError("subscription")

            return _check_public_subscription(
                sub
            )

        # --------------------------------------------------
        # Legacy complete token
        # id:expiry:sig
        # Supports historical 16 and 32 char signatures.
        # --------------------------------------------------

        if len(parts) == 3:
            sid_text, expiry_text, supplied = parts

            if (
                not sid_text.isdigit()
                or not expiry_text.lstrip("-").isdigit()
                or len(supplied) not in {16, 32}
            ):
                raise ValueError("legacy-format")

            payload = (
                f"{sid_text}:{expiry_text}"
            )

            expected_full = hmac.new(
                settings.app_secret_key.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()

            expected = expected_full[
                :len(supplied)
            ]

            if not hmac.compare_digest(
                supplied,
                expected,
            ):
                raise ValueError(
                    "legacy-signature"
                )

            sub = db.get(
                Subscription,
                int(sid_text),
            )

            if not sub:
                raise ValueError("subscription")

            current_expiry = (
                int(sub.expires_at.timestamp())
                if sub.expires_at
                else 0
            )

            if (
                int(expiry_text)
                != current_expiry
            ):
                raise ValueError(
                    "legacy-expiry"
                )

            return _check_public_subscription(
                sub
            )

        # --------------------------------------------------
        # Broken legacy token generated by old _share_token
        # id:sig
        #
        # The missing expiry can be reconstructed from the
        # current subscription because that is what the
        # old generator used while signing.
        # --------------------------------------------------

        if len(parts) == 2:
            sid_text, supplied = parts

            if (
                not sid_text.isdigit()
                or len(supplied) not in {16, 32}
            ):
                raise ValueError(
                    "broken-legacy-format"
                )

            sub = db.get(
                Subscription,
                int(sid_text),
            )

            if not sub:
                raise ValueError("subscription")

            current_expiry = (
                int(sub.expires_at.timestamp())
                if sub.expires_at
                else 0
            )

            payload = (
                f"{sid_text}:{current_expiry}"
            )

            expected_full = hmac.new(
                settings.app_secret_key.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()

            expected = expected_full[
                :len(supplied)
            ]

            if not hmac.compare_digest(
                supplied,
                expected,
            ):
                raise ValueError(
                    "broken-legacy-signature"
                )

            return _check_public_subscription(
                sub
            )

        raise ValueError("token-format")

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=404,
            detail="لینک اتصال معتبر نیست",
        )


def _share_url(db, sub: Subscription) -> str:
    from ..domain_models import Domain, DomainType

    subscription_domain = (
        db.query(Domain)
        .filter(Domain.domain_type == DomainType.SUBSCRIPTION)
        .filter(Domain.ssl_status == "ACTIVE")
        .first()
    )

    base = subscription_base_url(db)

    if not base:
        return (
            f"/v1/connect/"
            f"{_share_token(sub)}"
        )

    return (
        f"{base}/v1/connect/"
        f"{_share_token(sub)}"
    )


def _qr_data_uri(value: str) -> str:
    image = qrcode.make(value, image_factory=qrcode.image.svg.SvgPathImage, box_size=6, border=2)
    out = io.BytesIO()
    image.save(out)
    return "data:image/svg+xml;base64," + base64.b64encode(out.getvalue()).decode()


def _public_payload(db: Session, sub: Subscription) -> dict[str, Any]:
    info = _stored_info(db, sub)
    for cred in info["credentials"]:
        for item in cred.get("items", []):
            if cred["protocol"] == "wireguard" and item.get("config"):
                item["qr"] = _qr_data_uri(item["config"])
            elif cred["protocol"] == "v2ray" and item.get("uri"):
                item["qr"] = _qr_data_uri(item["uri"])
    info["subscription_link"] = _share_url(db, sub)
    info["expires_at"] = sub.expires_at.isoformat() if sub.expires_at else None
    info["traffic_limit_gb"] = round((sub.traffic_limit_bytes or 0) / 1024 / 1024 / 1024, 2)
    return info


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.app_secret_key.encode()).digest())
    return Fernet(key)


def _enc(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False).encode()
    return _fernet().encrypt(raw).decode()


def _dec(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(_fernet().decrypt(value.encode()).decode())
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return None


def _nodes(db: Session, sub: Subscription) -> list[Node]:
    # TWINPANEL_GLOBAL_NODE_DELIVERY_V1
    #
    # Servers are global infrastructure, not subscription-owned.
    # Every subscription receives every Node from the panel.
    return (
        db.query(Node).filter(Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )


def _protocols(db: Session, sub: Subscription) -> list[str]:
    return [r[0] for r in db.query(SubscriptionProtocol.protocol).filter(SubscriptionProtocol.subscription_id == sub.id).all()]


def _cfg(db: Session, node_id: int, protocol: str) -> NodeProtocolConfig | None:
    return db.query(NodeProtocolConfig).filter(NodeProtocolConfig.node_id == node_id, NodeProtocolConfig.protocol == protocol).first()


def _port(db: Session, node_id: int, protocol: str) -> int:
    cfg = _cfg(db, node_id, protocol)
    return int(cfg.port) if cfg and cfg.port else DEFAULT_PORTS[protocol]


def _transport(db: Session, node_id: int, protocol: str) -> str:
    cfg = _cfg(db, node_id, protocol)
    return (cfg.transport if cfg and cfg.transport else ("udp" if protocol in {"wireguard", "l2tp"} else "tcp")).lower()



def _node_host(node: Node) -> str:
    domain = (getattr(node, "public_domain", None) or "").strip().lower()
    if domain:
        domain = re.sub(r"^https?://", "", domain).split("/")[0].strip()
        if ":" in domain:
            domain = domain.split(":", 1)[0]
        if re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain):
            return domain
    return node.public_ip


# TWINPANEL_IRAN_EXIT_CLIENT_ACCESS_V2

_TUNNEL_PUBLIC_PORT_BASE = {
    "cisco": 20000,
    "openvpn": 21000,
    "wireguard": 22000,
    "v2ray": 23000,
}


def _tunnel_access_endpoint(
    db: Session,
    node: Node,
    protocol: str,
) -> tuple[str, int]:
    """
    User-facing VPN services run on EXIT nodes.

    The client connects to the Iran node belonging to the
    active Iran -> Exit tunnel.

    Control/Mother/Core nodes are never valid client endpoints.

    Example for Exit node 4:
      Cisco      Iran:20004 -> tunnel -> Exit:443
      OpenVPN    Iran:21004 -> tunnel -> Exit:1194
      WireGuard  Iran:22004 -> tunnel -> Exit:51820
      Xray       Iran:23004 -> tunnel -> Exit:8443

    L2TP/IPsec uses its dedicated Primary Iran -> Exit
    forwarding path on UDP 500/4500.
    """

    protocol = str(protocol).lower()

    # Protocols not yet supported through tunnel access
    # keep their previous behavior.
    if protocol not in _TUNNEL_PUBLIC_PORT_BASE:
        return (
            _node_host(node),
            _port(db, node.id, protocol),
        )

    # Only EXIT services need an Iran entry endpoint.
    if node.node_type != NodeType.EXIT:
        return (
            _node_host(node),
            _port(db, node.id, protocol),
        )

    # An Exit can have more than one active Iran tunnel.
    # Priority decides which Iran entry is delivered to users.
    tunnels = (
        db.query(Tunnel)
        .filter(
            Tunnel.exit_node_id == node.id,
            Tunnel.is_active.is_(True),
        )
        .order_by(
            Tunnel.priority.asc(),
            Tunnel.id.asc(),
        )
        .all()
    )

    selected_tunnel = None
    iran_node = None

    for tunnel in tunnels:
        candidate = db.get(
            Node,
            tunnel.iran_node_id,
        )

        if not candidate:
            continue

        if candidate.node_type != NodeType.IRAN:
            continue

        # TWINPANEL_TUNNEL_FIRST_DELIVERY_V2
        #
        # Public delivery policy is based on assignment:
        #
        #   active tunnel assignment -> Iran/Tunnel endpoint
        #   no tunnel assignment     -> direct Exit endpoint
        #
        # Runtime health is handled separately by monitoring.
        if (
            getattr(
                candidate,
                "retired_at",
                None,
            )
            is not None
        ):
            continue

        # The Twinpanel/API server is Control Plane only.
        if (
            getattr(candidate, "agent_url", None)
            == "local://core"
        ):
            continue

        if getattr(
            candidate,
            "is_mother",
            False,
        ):
            continue

        selected_tunnel = tunnel
        iran_node = candidate
        break

    if selected_tunnel is None or iran_node is None:
        # TWINPANEL_DIRECT_EXIT_FALLBACK_V1
        #
        # Dual access mode:
        #
        #   active tunnel:
        #       Client -> Iran -> Exit
        #
        #   no active tunnel:
        #       Client -> Exit directly
        #
        # Egress/Outbound is independent from ingress mode
        # and remains on this Exit node.
        return (
            _node_host(node),
            _port(
                db,
                node.id,
                protocol,
            ),
        )

    # public_domain takes precedence automatically.
    # If no domain is configured, public_ip is used.
    host = _node_host(iran_node)

    if (
        not host
        or host
        in {
            "127.0.0.1",
            "localhost",
        }
    ):
        raise RuntimeError(
            (
                "Iran tunnel endpoint is invalid "
                f"for node {iran_node.id}"
            )
        )

    public_port = (
        _TUNNEL_PUBLIC_PORT_BASE[protocol]
        + int(node.id)
    )

    if not 1 <= public_port <= 65535:
        raise RuntimeError(
            (
                "Generated tunnel access port "
                f"is invalid: {public_port}"
            )
        )

    return host, public_port


# TWINPANEL_USERNAME_POLICY_V2
def _safe_username(sub: Subscription, user: User) -> str:
    try:
        from .general_settings import (
            build_subscription_username_runtime,
        )

        return build_subscription_username_runtime(
            sub.id,
            user.id,
        )

    except Exception:
        raw = f"mv{sub.id}_{user.id}"

        return re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            raw,
        )[:30]


async def _cisco(db: Session, node: Node, sub: Subscription, user: User, username: str, password: str) -> dict[str, Any]:
    conn = await ssh_connect_saved(node, db)
    try:
        encoded = base64.b64encode((password + "\n" + password + "\n").encode()).decode()
        await cmd(conn, f"printf '%s' {shlex.quote(encoded)} | base64 -d | ocpasswd -c /etc/ocserv/ocpasswd {shlex.quote(username)}")
        host, port = _tunnel_access_endpoint(
            db,
            node,
            "cisco",
        )
        return {
            "node_id": node.id,
            "node": node.name,
            "server": host,
            "server_ip": host,
            "port": port,
            "username": username,
            "password": password,
        }
    finally:
        conn.close(); await conn.wait_closed()


# TWINPANEL_L2TP_IRAN_ENTRY_V1
def _l2tp_tunnel_access_host(
    db: Session,
    node: Node,
) -> str:

    if node.node_type != NodeType.EXIT:
        return _node_host(node)

    # Import at runtime to avoid router import cycles.
    from .tunnels import _l2tp_primary_tunnel_id

    tunnels = (
        db.query(Tunnel)
        .filter(
            Tunnel.exit_node_id == node.id,
            Tunnel.is_active.is_(True),
        )
        .order_by(
            Tunnel.priority.asc(),
            Tunnel.id.asc(),
        )
        .all()
    )

    for tunnel in tunnels:

        # TWINPANEL_L2TP_DELIVERY_ASSIGNMENT_FIRST_V2
        #
        # _l2tp_primary_tunnel_id() intentionally requires an
        # ONLINE tunnel because it controls real routing.
        #
        # Subscription delivery has different semantics:
        # if an active Iran -> Exit tunnel is assigned, publish
        # that Iran ingress. Do not make displayed connection
        # info depend on runtime health.
        iran_node = db.get(
            Node,
            tunnel.iran_node_id,
        )

        if not iran_node:
            continue

        if iran_node.node_type != NodeType.IRAN:
            continue

        # TWINPANEL_L2TP_TUNNEL_FIRST_DELIVERY_V2
        #
        # Keep the configured Iran ingress visible while its
        # active tunnel assignment exists. Retired nodes remain
        # invalid delivery endpoints.
        if (
            getattr(
                iran_node,
                "retired_at",
                None,
            )
            is not None
        ):
            continue

        if getattr(
            iran_node,
            "is_mother",
            False,
        ):
            continue

        if (
            getattr(
                iran_node,
                "agent_url",
                None,
            )
            == "local://core"
        ):
            continue

        host = _node_host(iran_node)

        if (
            not host
            or host in {
                "127.0.0.1",
                "localhost",
            }
        ):
            continue

        return host

    # No active Iran tunnel: L2TP connects directly
    # to the Exit node. Outbound routing on the Exit
    # remains responsible for Internet egress.
    return _node_host(node)


async def _l2tp(db: Session, node: Node, sub: Subscription, user: User, username: str, password: str) -> dict[str, Any]:
    conn = await ssh_connect_saved(node, db)
    try:
        line = f'{username} * {password} *'
        b64 = base64.b64encode((line + "\n").encode()).decode()
        await cmd(
            conn,
            f"grep -v '^{re.escape(username)}[[:space:]]' /etc/ppp/chap-secrets > /tmp/mvchap.$$ || true; "
            f"printf '%s' {shlex.quote(b64)} | base64 -d >> /tmp/mvchap.$$; "
            f"cat /tmp/mvchap.$$ > /etc/ppp/chap-secrets; "
            f"rm -f /tmp/mvchap.$$; chmod 600 /etc/ppp/chap-secrets"
        )

        # TWINPANEL_ACCOUNT_CENTRAL_L2TP_PSK_V1
        # One source of truth for all L2TP Exit nodes.
        psk = get_or_create_l2tp_psk(db)

        if not psk:
            raise RuntimeError(
                "Central L2TP IPsec Secret is empty"
            )

        host = _l2tp_tunnel_access_host(
            db,
            node,
        )

        return {
            "node_id": node.id,
            "node": node.name,
            "server": host,
            "server_ip": host,
            "ports": "500/4500 UDP",
            "username": username,
            "password": password,
            "psk": psk,
        }
    finally:
        conn.close()
        await conn.wait_closed()


async def _xray(db: Session, node: Node, sub: Subscription, user: User, client_id: str) -> dict[str, Any]:
    conn = await ssh_connect_saved(node, db)
    try:
        email = f"mv-{sub.id}@twinpanel"
        py = f'''import json\np='/usr/local/etc/xray/config.json'\nd=json.load(open(p))\nclients=d['inbounds'][0]['settings'].setdefault('clients',[])\nclients[:]=[c for c in clients if c.get('email')!={email!r}]\nclients.append({{'id':{client_id!r},'email':{email!r}}})\njson.dump(d,open(p,'w'),indent=2)\n'''
        b64=base64.b64encode(py.encode()).decode()
        await cmd(conn, f"printf '%s' {shlex.quote(b64)} | base64 -d | python3 && systemctl restart xray")
        host, port = _tunnel_access_endpoint(
            db,
            node,
            "v2ray",
        )
        # TWINPANEL_V2RAY_ACCOUNT_COUNTRY_NAME_V1
        username_part = _download_filename_part(
            sub.account_username
            or _safe_username(sub, user),
            f"user{sub.id}",
        )

        country_part = _country_download_name(node)

        profile_name = (
            f"{username_part}-{country_part}"
        )

        uri = (
            f"vless://{client_id}@{host}:{port}"
            f"?encryption=none&type=tcp"
            f"#{profile_name}"
        )
        return {
            "node_id": node.id,
            "node": node.name,
            "server": host,
            "server_ip": host,
            "port": port,
            "uuid": client_id,
            "uri": uri,
        }
    finally:
        conn.close(); await conn.wait_closed()


async def _openvpn(
    db: Session,
    node: Node,
    sub: Subscription,
    user: User,
) -> dict[str, Any]:

    central_enabled = (
        is_openvpn_central_pki_enabled(
            db
        )
    )

    if central_enabled:
        identity = (
            get_or_create_openvpn_client_identity(
                db,
                sub.id,
            )
        )

        ca = identity[
            "ca_certificate"
        ]

        cert = identity[
            "client_certificate"
        ]

        key = identity[
            "client_private_key"
        ]

    else:
        # Legacy migration-safe path.
        # تا زمان فعال‌شدن Central PKI همان EasyRSA
        # فعلی Exit بدون تغییر استفاده می‌شود.
        conn = await ssh_connect_saved(
            node,
            db,
        )

        try:
            cn = f"mv{sub.id}n{node.id}"

            await cmd(
                conn,
                (
                    "cd /etc/openvpn/easy-rsa && "
                    f"test -f pki/issued/{shlex.quote(cn)}.crt || "
                    "EASYRSA_BATCH=1 "
                    "./easyrsa build-client-full "
                    f"{shlex.quote(cn)} "
                    "nopass >/dev/null"
                ),
                timeout=300,
            )

            ca = await cmd(
                conn,
                (
                    "cat "
                    "/etc/openvpn/easy-rsa/"
                    "pki/ca.crt"
                ),
            )

            cert = await cmd(
                conn,
                (
                    "sed -n "
                    "'/BEGIN CERTIFICATE/,"
                    "/END CERTIFICATE/p' "
                    "/etc/openvpn/easy-rsa/"
                    f"pki/issued/{shlex.quote(cn)}.crt"
                ),
            )

            key = await cmd(
                conn,
                (
                    "cat "
                    "/etc/openvpn/easy-rsa/"
                    f"pki/private/{shlex.quote(cn)}.key"
                ),
            )

        finally:
            conn.close()
            await conn.wait_closed()

    transport = _transport(
        db,
        node.id,
        "openvpn",
    )

    proto = (
        "udp"
        if "udp" in transport
        else "tcp-client"
    )

    host, port = _tunnel_access_endpoint(
        db,
        node,
        "openvpn",
    )

    config = f'''client
dev tun
proto {proto}
remote {host} {port}
redirect-gateway def1
tun-mtu 1200
mssfix 1160
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
verb 3
data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305
auth SHA256
<ca>
{ca}
</ca>
<cert>
{cert}
</cert>
<key>
{key}
</key>
'''

    return {
        "node_id": node.id,
        "node": node.name,
        "server": host,
        "server_ip": host,
        "port": port,
        "transport": transport,
        "central_pki": central_enabled,
        "filename": _account_country_filename(
            sub,
            user,
            node,
            "ovpn",
        ),
        "config": config,
    }


# TWINPANEL_ACCOUNT_COUNTRY_FILENAME_V1
_COUNTRY_DOWNLOAD_NAMES = {
    "DE": "Germany",
    "NL": "Netherlands",
    "FR": "France",
    "GB": "United-Kingdom",
    "UK": "United-Kingdom",
    "US": "United-States",
    "CA": "Canada",
    "FI": "Finland",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "CH": "Switzerland",
    "AT": "Austria",
    "BE": "Belgium",
    "PL": "Poland",
    "CZ": "Czech-Republic",
    "RO": "Romania",
    "BG": "Bulgaria",
    "HU": "Hungary",
    "IT": "Italy",
    "ES": "Spain",
    "PT": "Portugal",
    "GR": "Greece",
    "TR": "Turkey",
    "AE": "UAE",
    "SG": "Singapore",
    "JP": "Japan",
    "KR": "South-Korea",
    "HK": "Hong-Kong",
    "IN": "India",
    "AU": "Australia",
    "IR": "Iran",
}


def _download_filename_part(value: Any, fallback: str) -> str:
    value = str(value or "").strip()

    value = re.sub(
        r"\s+",
        "-",
        value,
    )

    value = re.sub(
        r"[^A-Za-z0-9._-]",
        "-",
        value,
    )

    value = re.sub(
        r"-+",
        "-",
        value,
    ).strip("._-")

    return value or fallback


def _country_download_name(node: Node) -> str:
    code = str(
        getattr(node, "country_code", "")
        or ""
    ).strip().upper()

    if code in _COUNTRY_DOWNLOAD_NAMES:
        return _COUNTRY_DOWNLOAD_NAMES[code]

    if code and code != "CORE":
        return _download_filename_part(
            code,
            "Server",
        )

    return _download_filename_part(
        getattr(node, "name", None),
        "Server",
    )


def _account_country_filename(
    sub: Subscription,
    user: User,
    node: Node,
    extension: str,
) -> str:
    username = (
        sub.account_username
        or _safe_username(sub, user)
    )

    username = _download_filename_part(
        username,
        f"user{sub.id}",
    )

    country = _country_download_name(node)

    extension = str(extension).lstrip(".")

    return f"{username}-{country}.{extension}"


async def _wireguard(db: Session, node: Node, sub: Subscription, user: User) -> dict[str, Any]:
    conn=await ssh_connect_saved(node,db)
    try:
        private=(await cmd(conn,"wg genkey")).strip()
        public=(await cmd(conn,f"printf '%s' {shlex.quote(private)} | wg pubkey")).strip()
        used=await cmd(conn,"wg show wg-access0 allowed-ips",check=False)
        taken=set()
        for line in used.splitlines():
            m=re.search(r"10\.93\.0\.(\d+)",line)
            if m: taken.add(int(m.group(1)))
        host=next((i for i in range(2,255) if i not in taken),None)
        if host is None: raise RuntimeError("WireGuard address pool is full")
        address=f"10.93.0.{host}/32"
        await cmd(conn,f"wg set wg-access0 peer {shlex.quote(public)} allowed-ips {address}")
        peer=f'''\n[Peer]\nPublicKey = {public}\nAllowedIPs = {address}\n'''
        b64=base64.b64encode(peer.encode()).decode()
        await cmd(conn,f"printf '%s' {shlex.quote(b64)} | base64 -d >> /etc/wireguard/wg-access0.conf")
        server_pub=(await cmd(conn,"cat /etc/wireguard/wg-access0.key | wg pubkey")).strip()
        host, port = _tunnel_access_endpoint(
            db,
            node,
            "wireguard",
        )

        config = f'''[Interface]
PrivateKey = {private}
Address = {address}
MTU = 1280
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = {server_pub}
Endpoint = {host}:{port}
AllowedIPs = 0.0.0.0/1, 128.0.0.0/1
PersistentKeepalive = 25
'''

        return {
            "node_id": node.id,
            "node": node.name,
            "server": host,
            "server_ip": host,
            "port": port,
            "address": address,
            "filename": _account_country_filename(
                sub,
                user,
                node,
                "conf",
            ),
            "config": config,
        }
    finally:
        conn.close(); await conn.wait_closed()



# TWINPANEL_LIVE_IRAN_INGRESS_V1
def _live_client_item(
    db: Session,
    sub: Subscription,
    protocol: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    """
    Rebuild the user-facing endpoint at read time.

    Stored credentials keep cryptographic identity/config,
    while host/port always follow the current Iran ingress
    attached to the Exit tunnel.
    """

    if not isinstance(item, dict):
        return item

    result = dict(item)

    try:
        node_id = int(
            result.get("node_id")
        )
    except (TypeError, ValueError):
        return result

    node = db.get(
        Node,
        node_id,
    )

    # Never rewrite a legacy Mother/Iran credential as if it
    # were an Exit credential. Those must be reconciled first.
    if (
        not node
        or node.node_type != NodeType.EXIT
    ):
        return result

    protocol = str(
        protocol
        or ""
    ).strip().lower()

    try:

        # ---------------------------------------------
        # L2TP has no custom public service port.
        # ---------------------------------------------
        if protocol == "l2tp":
            host = _l2tp_tunnel_access_host(
                db,
                node,
            )

            result["server"] = host
            result["server_ip"] = host

            return result

        # ---------------------------------------------
        # Cisco / OpenVPN / WireGuard / V2Ray
        # ---------------------------------------------
        if protocol not in _TUNNEL_PUBLIC_PORT_BASE:
            return result

        host, port = _tunnel_access_endpoint(
            db,
            node,
            protocol,
        )

        result["server"] = host
        result["server_ip"] = host
        result["port"] = port

        # ---------------------------------------------
        # OpenVPN
        # Preserve certificates and keys.
        # Only replace the remote endpoint.
        # ---------------------------------------------
        if (
            protocol == "openvpn"
            and result.get("config")
        ):
            config = str(
                result["config"]
            )

            config = re.sub(
                r"(?m)^remote\s+\S+\s+\d+\s*$",
                f"remote {host} {port}",
                config,
                count=1,
            )

            result["config"] = config

        # ---------------------------------------------
        # WireGuard
        # Preserve PrivateKey/PublicKey/address.
        # Only replace Endpoint.
        # ---------------------------------------------
        elif (
            protocol == "wireguard"
            and result.get("config")
        ):
            config = str(
                result["config"]
            )

            config = re.sub(
                r"(?m)^Endpoint\s*=\s*.+$",
                f"Endpoint = {host}:{port}",
                config,
                count=1,
            )

            result["config"] = config

        # ---------------------------------------------
        # V2Ray / VLESS
        # Preserve UUID + query + profile name.
        # Replace only authority host:port.
        # ---------------------------------------------
        elif (
            protocol == "v2ray"
            and result.get("uri")
        ):
            uri = str(
                result["uri"]
            )

            uri = re.sub(
                r"^(vless://[^@]+@)[^:/?#]+:\d+",
                rf"\g<1>{host}:{port}",
                uri,
                count=1,
            )

            result["uri"] = uri

        return result

    except Exception:
        # Delivery must not destroy an otherwise valid
        # stored credential if live endpoint lookup has
        # a temporary control-plane problem.
        return result



# TWINPANEL_L2TP_CREDENTIAL_SELF_HEAL_V1
async def _ensure_l2tp_credential(
    db: Session,
    sub: Subscription,
) -> bool:
    """
    Ensure a selected L2TP subscription always has a usable,
    active ProtocolCredential.

    A temporary tunnel/control-plane failure must not permanently
    remove L2TP from connection-info.
    """

    selected_protocols = {
        str(item).strip().lower()
        for item in _protocols(db, sub)
    }

    if "l2tp" not in selected_protocols:
        return False

    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == sub.id,
            ProtocolCredential.protocol == "l2tp",
        )
        .first()
    )

    # Reuse an already-created L2TP credential when its payload
    # is still valid. _stored_info() will refresh the live Iran
    # ingress and central PSK before exposing it.
    if cred and cred.config_text_encrypted:
        try:
            existing = _dec(
                cred.config_text_encrypted
            )
        except Exception:
            existing = None

        valid_existing = (
            isinstance(existing, dict)
            and bool(existing)
        ) or (
            isinstance(existing, list)
            and any(
                isinstance(item, dict)
                and bool(item)
                for item in existing
            )
        )

        if valid_existing:
            if not cred.is_active:
                cred.is_active = True
                db.commit()

            return True

    user = db.get(
        User,
        sub.user_id,
    )

    if not user:
        return False

    nodes = [
        node
        for node in _nodes(db, sub)
        if (
            node.node_type == NodeType.EXIT
            and bool(
                getattr(
                    node,
                    "enable_l2tp",
                    False,
                )
            )
        )
    ]

    if not nodes:
        return False

    username = (
        sub.account_username
        or _safe_username(
            sub,
            user,
        )
    )

    if not sub.account_username:
        sub.account_username = username

    password = (
        sub.account_password_encrypted
        or _numeric_secret(8)
    )

    if not sub.account_password_encrypted:
        sub.account_password_encrypted = password

    items = []
    errors = []

    for node in nodes:
        try:
            item = await _l2tp(
                db,
                node,
                sub,
                user,
                username,
                password,
            )

            if isinstance(item, dict):
                items.append(item)

        except Exception as exc:
            errors.append(
                f"node={node.id}:{str(exc)[:250]}"
            )

    if not items:
        if errors:
            print(
                f"[L2TPSelfHeal] failed "
                f"subscription={sub.id} "
                + " | ".join(errors),
                flush=True,
            )

        # Do not break connection-info for the other protocols.
        return False

    if not cred:
        cred = ProtocolCredential(
            subscription_id=sub.id,
            protocol="l2tp",
        )
        db.add(cred)

    cred.username = username
    cred.secret_encrypted = _enc({
        "password": password,
    })
    cred.config_text_encrypted = _enc(items)
    cred.is_active = True

    db.commit()

    print(
        f"[L2TPSelfHeal] success "
        f"subscription={sub.id} "
        f"nodes={len(items)}",
        flush=True,
    )

    return True



# TWINPANEL_DELIVERY_USABLE_NODE_FILTER_V61
def _delivery_state_value(value: Any) -> str:
    value = getattr(
        value,
        "value",
        value,
    )

    return str(
        value
        or ""
    ).strip().lower()


def _delivery_active_tunnels(
    db: Session,
    exit_node: Node,
) -> list[Tunnel]:
    """
    Return only actually usable Iran -> Exit tunnels.

    A stale credential must never make an offline/unrouted
    Exit visible to a customer.
    """

    tunnels = (
        db.query(Tunnel)
        .filter(
            Tunnel.exit_node_id
            == exit_node.id,
            Tunnel.is_active.is_(True),
        )
        .order_by(
            Tunnel.priority.asc(),
            Tunnel.id.asc(),
        )
        .all()
    )

    usable = []

    for tunnel in tunnels:

        if (
            _delivery_state_value(
                tunnel.status
            )
            != "online"
        ):
            continue

        iran_node = db.get(
            Node,
            tunnel.iran_node_id,
        )

        if not iran_node:
            continue

        if (
            iran_node.node_type
            != NodeType.IRAN
        ):
            continue

        if (
            _delivery_state_value(
                iran_node.status
            )
            != "online"
        ):
            continue

        if getattr(
            iran_node,
            "retired_at",
            None,
        ):
            continue

        if getattr(
            iran_node,
            "is_mother",
            False,
        ):
            continue

        if (
            getattr(
                iran_node,
                "agent_url",
                None,
            )
            == "local://core"
        ):
            continue

        usable.append(
            tunnel
        )

    return usable


def _delivery_item_is_usable(
    db: Session,
    protocol: str,
    item: dict[str, Any],
) -> bool:
    """
    Customer delivery guard.

    Hide:
      - missing / retired nodes
      - hidden nodes
      - offline Exit nodes
      - Exit nodes without a usable Iran tunnel
      - non-primary L2TP Exit nodes

    Stored credentials are left untouched.
    """

    if not isinstance(
        item,
        dict,
    ):
        return False

    try:
        node_id = int(
            item.get(
                "node_id"
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    node = db.get(
        Node,
        node_id,
    )

    if not node:
        return False

    if getattr(
        node,
        "retired_at",
        None,
    ):
        return False

    if not bool(
        getattr(
            node,
            "show_to_users",
            True,
        )
    ):
        return False

    if (
        _delivery_state_value(
            node.status
        )
        != "online"
    ):
        return False

    # Customer server items must resolve to Exit nodes.
    if (
        node.node_type
        != NodeType.EXIT
    ):
        return False

    protocol = str(
        protocol
        or ""
    ).strip().lower()

    tunnels = (
        _delivery_active_tunnels(
            db,
            node,
        )
    )

    # TWINPANEL_DELIVERY_DIRECT_EXIT_FALLBACK_V1
    #
    # No usable Iran ingress does NOT invalidate an otherwise
    # healthy Exit credential. In that situation the client is
    # delivered the Exit endpoint directly.
    if not tunnels:

        protocol_flag = {
            "cisco":
                "enable_cisco",
            "openvpn":
                "enable_openvpn",
            "wireguard":
                "enable_wireguard",
            "l2tp":
                "enable_l2tp",
            "v2ray":
                "enable_v2ray",
        }.get(
            protocol
        )

        if not protocol_flag:
            return False

        if not bool(
            getattr(
                node,
                protocol_flag,
                False,
            )
        ):
            return False

        cfg = _cfg(
            db,
            node.id,
            protocol,
        )

        if not cfg:
            return False

        if (
            _delivery_state_value(
                getattr(
                    cfg,
                    "status",
                    None,
                )
            )
            != "online"
        ):
            return False

        return True

    # UDP 500/4500 cannot be DNATed to multiple Exit nodes
    # behind the same Iran public address at the same time.
    # Only the configured Primary L2TP tunnel is exposed.
    if protocol == "l2tp":

        from .tunnels import (
            _l2tp_primary_tunnel_id,
        )

        for tunnel in tunnels:

            primary_id = (
                _l2tp_primary_tunnel_id(
                    db,
                    tunnel.iran_node_id,
                )
            )

            if (
                primary_id
                == int(tunnel.id)
            ):
                return True

        return False

    return True


def _stored_info(
    db: Session,
    sub: Subscription,
) -> dict[str, Any]:

    # TWINPANEL_L2TP_LIVE_CENTRAL_PSK_V1
    # L2TP PSK is global. Never trust a PSK cached inside an old
    # ProtocolCredential; always expose the current central PSK.

    data = []
    current_l2tp_psk = None

    rows = (
        db.query(
            ProtocolCredential
        )
        .filter(
            ProtocolCredential.subscription_id
            == sub.id,
            ProtocolCredential.is_active.is_(True),
        )
        .all()
    )

    for row in rows:

        payload = _dec(
            row.config_text_encrypted
        )

        if not payload:
            continue

        protocol_key = str(
            row.protocol
            or ""
        ).strip().lower()

        source_items = (
            payload
            if isinstance(
                payload,
                list,
            )
            else [payload]
        )

        filtered_items = []

        for item in source_items:

            if not isinstance(
                item,
                dict,
            ):
                continue

            live_item = (
                _live_client_item(
                    db,
                    sub,
                    protocol_key,
                    item,
                )
            )

            if not (
                _delivery_item_is_usable(
                    db,
                    protocol_key,
                    live_item,
                )
            ):
                continue

            filtered_items.append(
                live_item
            )

        if not filtered_items:
            continue

        if protocol_key == "l2tp":

            if (
                current_l2tp_psk
                is None
            ):
                current_l2tp_psk = (
                    get_or_create_l2tp_psk(
                        db
                    )
                )

            for item in filtered_items:
                item["psk"] = (
                    current_l2tp_psk
                )

        if isinstance(
            payload,
            list,
        ):
            final_payload = (
                filtered_items
            )
        else:
            final_payload = (
                filtered_items[0]
            )

        data.append({
            "protocol":
                row.protocol,

            "username":
                row.username,

            "items":
                final_payload,
        })

    return {
        "subscription_id":
            sub.id,

        "credentials":
            data,

        "downloads":
            DOWNLOADS,

        "subscription_link":
            _share_url(
                db,
                sub,
            ),

        "account": {
            "username":
                sub.account_username,

            "password":
                sub.account_password_encrypted,
        },
    }




@customer_router.get("/{subscription_id}/connection-info")
async def customer_connection_info(
    subscription_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, subscription_id)

    if not sub or sub.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    status_value = getattr(
        sub.status,
        "value",
        str(sub.status),
    )

    if status_value != "active":
        raise HTTPException(
            status_code=403,
            detail="اشتراک فعال نیست",
        )

    if (
        sub.expires_at
        and sub.expires_at <= datetime.utcnow()
    ):
        raise HTTPException(
            status_code=403,
            detail="اشتراک منقضی شده است",
        )

    # TWINPANEL_L2TP_CONNECTION_INFO_SELF_HEAL_V1
    await _ensure_l2tp_credential(
        db,
        sub,
    )

    return _stored_info(db, sub)


@router.get("/{subscription_id}/connection-info")
async def connection_info(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    # TWINPANEL_L2TP_ADMIN_CONNECTION_INFO_SELF_HEAL_V1
    await _ensure_l2tp_credential(
        db,
        sub,
    )

    return _stored_info(
        db,
        sub,
    )



# ============================================================
# TWINPANEL_INSTALLED_NODE_SUBSCRIPTION_AUTOSYNC_V1
# ============================================================

def _autosync_enum_value(value) -> str:
    return str(
        getattr(
            value,
            "value",
            value,
        )
        or ""
    ).strip().lower()


def _autosync_credential_items(
    cred: ProtocolCredential | None,
) -> list[dict[str, Any]]:

    if not cred:
        return []

    raw = _dec(
        cred.config_text_encrypted
    )

    if isinstance(raw, list):
        return [
            dict(item)
            for item in raw
            if isinstance(item, dict)
        ]

    if isinstance(raw, dict):

        nested = raw.get(
            "items"
        )

        if isinstance(nested, list):
            return [
                dict(item)
                for item in nested
                if isinstance(item, dict)
            ]

        if raw:
            return [
                dict(raw)
            ]

    return []


def _autosync_item_node_id(
    item: dict[str, Any],
) -> int:

    try:
        return int(
            item.get("node_id")
            or 0
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0


def remove_node_from_delivery_credentials(
    db: Session,
    node_id: int,
) -> dict[str, Any]:
    """
    Remove a retired Node only from mutable user-facing
    credential payloads.

    Quota/session/usage history is intentionally untouched.
    """

    node_id = int(
        node_id
    )

    credentials = (
        db.query(
            ProtocolCredential
        )
        .filter(
            ProtocolCredential
            .config_text_encrypted
            .isnot(None)
        )
        .all()
    )

    changed_credentials = 0
    removed_items = 0

    for cred in credentials:

        items = (
            _autosync_credential_items(
                cred
            )
        )

        if not items:
            continue

        kept = []
        removed_here = 0

        for item in items:

            if (
                _autosync_item_node_id(
                    item
                )
                == node_id
            ):
                removed_here += 1
                continue

            kept.append(
                item
            )

        if not removed_here:
            continue

        removed_items += (
            removed_here
        )

        changed_credentials += 1

        cred.config_text_encrypted = (
            _enc(kept)
            if kept
            else None
        )

        cred.is_active = bool(
            kept
        )

    db.flush()

    return {
        "ok": True,
        "node_id": node_id,
        "changed_credentials":
            changed_credentials,
        "removed_items":
            removed_items,
    }


async def sync_installed_node_to_subscriptions(
    db: Session,
    node: Node,
) -> dict[str, Any]:
    """
    Keep an installed Node synchronized with subscriptions.

    IRAN:
      - membership only
      - may become legacy iran_node_id reference
      - never creates user VPN credentials

    EXIT:
      - membership for every subscription
      - create only the missing credential pair on THIS Exit
      - existing Exit credentials are preserved
      - quota refresh runs after a new pair is created
    """

    if not node:
        return {
            "ok": False,
            "error": "node_missing",
        }

    if getattr(
        node,
        "retired_at",
        None,
    ) is not None:
        return {
            "ok": False,
            "error": "node_retired",
        }

    node_type = (
        _autosync_enum_value(
            node.node_type
        )
    )

    if node_type not in {
        "iran",
        "exit",
    }:
        return {
            "ok": True,
            "skipped": True,
            "reason":
                "unsupported_node_type",
        }

    all_subscriptions = (
        db.query(
            Subscription
        )
        .order_by(
            Subscription.id.asc()
        )
        .all()
    )

    membership_added = 0
    compatibility_updated = 0

    # --------------------------------------------------------
    # Membership / compatibility references
    # --------------------------------------------------------

    for sub in all_subscriptions:

        membership = (
            db.query(
                SubscriptionNode
            )
            .filter(
                SubscriptionNode.subscription_id
                == sub.id,

                SubscriptionNode.node_id
                == node.id,
            )
            .first()
        )

        if not membership:

            db.add(
                SubscriptionNode(
                    subscription_id=sub.id,
                    node_id=node.id,
                )
            )

            membership_added += 1

        if node_type == "exit":

            current = (
                db.get(
                    Node,
                    sub.exit_node_id,
                )
                if sub.exit_node_id
                else None
            )

            if (
                current is None
                or getattr(
                    current,
                    "retired_at",
                    None,
                )
                is not None
            ):
                sub.exit_node_id = (
                    node.id
                )

                compatibility_updated += 1

        elif (
            node_type == "iran"
            and not getattr(
                node,
                "is_mother",
                False,
            )
            and getattr(
                node,
                "agent_url",
                None,
            )
            != "local://core"
        ):

            current = (
                db.get(
                    Node,
                    sub.iran_node_id,
                )
                if sub.iran_node_id
                else None
            )

            current_is_control = (
                current is not None
                and (
                    getattr(
                        current,
                        "is_mother",
                        False,
                    )
                    or getattr(
                        current,
                        "agent_url",
                        None,
                    )
                    == "local://core"
                )
            )

            if (
                current is None
                or current_is_control
                or getattr(
                    current,
                    "retired_at",
                    None,
                )
                is not None
            ):
                sub.iran_node_id = (
                    node.id
                )

                compatibility_updated += 1

    db.commit()

    # Iran is tunnel/relay only.
    if node_type != "exit":

        return {
            "ok": True,
            "node_id": int(node.id),
            "node_type": node_type,
            "membership_added":
                membership_added,
            "compatibility_updated":
                compatibility_updated,
            "provisioned_pairs": 0,
            "reused_pairs": 0,
            "failed": [],
        }

    # --------------------------------------------------------
    # EXIT user credential provisioning
    # --------------------------------------------------------

    field_map = {
        "cisco":
            "enable_cisco",

        "openvpn":
            "enable_openvpn",

        "wireguard":
            "enable_wireguard",

        "l2tp":
            "enable_l2tp",

        "v2ray":
            "enable_v2ray",
    }

    active_ids = [
        int(sub.id)
        for sub in all_subscriptions
        if (
            _autosync_enum_value(
                sub.status
            )
            == "active"
        )
    ]

    provisioned_pairs = 0
    reused_pairs = 0
    failed = []

    for subscription_id in active_ids:

        db.expire_all()

        sub = db.get(
            Subscription,
            subscription_id,
        )

        if not sub:
            continue

        protocols = [
            str(protocol)
            .strip()
            .lower()

            for protocol
            in _protocols(
                db,
                sub,
            )

            if str(
                protocol
            ).strip()
        ]

        if not protocols:
            continue

        user = db.get(
            User,
            sub.user_id,
        )

        if not user:

            failed.append({
                "subscription_id":
                    subscription_id,
                "error":
                    "user_not_found",
            })

            continue

        username = (
            sub.account_username
            or _safe_username(
                sub,
                user,
            )
        )

        password = (
            sub.account_password_encrypted
            or _numeric_secret(8)
        )

        if not sub.account_username:
            sub.account_username = (
                username
            )

        if not sub.account_password_encrypted:
            sub.account_password_encrypted = (
                password
            )

        added_for_subscription = False

        for protocol in protocols:

            field_name = (
                field_map.get(
                    protocol
                )
            )

            if not field_name:
                continue

            if not bool(
                getattr(
                    node,
                    field_name,
                    False,
                )
            ):
                continue

            cred = (
                db.query(
                    ProtocolCredential
                )
                .filter(
                    ProtocolCredential.subscription_id
                    == sub.id,

                    ProtocolCredential.protocol
                    == protocol,
                )
                .first()
            )

            items = (
                _autosync_credential_items(
                    cred
                )
            )

            # Drop only stale/retired/non-exit delivery items.
            cleaned_items = []

            for item in items:

                item_node_id = (
                    _autosync_item_node_id(
                        item
                    )
                )

                item_node = (
                    db.get(
                        Node,
                        item_node_id,
                    )
                    if item_node_id
                    else None
                )

                if (
                    item_node
                    and item_node.node_type
                    == NodeType.EXIT
                    and getattr(
                        item_node,
                        "retired_at",
                        None,
                    )
                    is None
                ):
                    cleaned_items.append(
                        item
                    )

            items = cleaned_items

            already_exists = any(
                _autosync_item_node_id(
                    item
                )
                == int(node.id)

                for item in items
            )

            if already_exists:

                reused_pairs += 1

                if cred:
                    cred.config_text_encrypted = (
                        _enc(items)
                    )

                    cred.is_active = True

                continue

            try:

                if protocol == "cisco":

                    item = await _cisco(
                        db,
                        node,
                        sub,
                        user,
                        username,
                        password,
                    )

                elif protocol == "openvpn":

                    item = await _openvpn(
                        db,
                        node,
                        sub,
                        user,
                    )

                elif protocol == "wireguard":

                    item = await _wireguard(
                        db,
                        node,
                        sub,
                        user,
                    )

                elif protocol == "l2tp":

                    item = await _l2tp(
                        db,
                        node,
                        sub,
                        user,
                        username,
                        password,
                    )

                elif protocol == "v2ray":

                    item = await _xray(
                        db,
                        node,
                        sub,
                        user,
                        str(
                            uuid.uuid4()
                        ),
                    )

                else:
                    continue

            except Exception as exc:

                failed.append({
                    "subscription_id":
                        subscription_id,
                    "protocol":
                        protocol,
                    "node_id":
                        int(node.id),
                    "error":
                        str(exc)[:800],
                })

                continue

            if not cred:

                cred = (
                    ProtocolCredential(
                        subscription_id=
                            sub.id,
                        protocol=
                            protocol,
                    )
                )

                db.add(
                    cred
                )

            items.append(
                item
            )

            cred.config_text_encrypted = (
                _enc(items)
            )

            cred.is_active = True

            if protocol in {
                "cisco",
                "l2tp",
            }:

                cred.username = (
                    username
                )

                cred.secret_encrypted = (
                    _enc({
                        "password":
                            password
                    })
                )

            provisioned_pairs += 1
            added_for_subscription = True

        db.commit()

        if added_for_subscription:

            try:

                from ..services.quota_refresh import (
                    sync_subscription_quota_nodes
                )

                quota_result = (
                    await sync_subscription_quota_nodes(
                        db,
                        sub.id,
                    )
                )

                if not quota_result.get(
                    "ok",
                    False,
                ):

                    failed.append({
                        "subscription_id":
                            subscription_id,
                        "protocol":
                            "quota",
                        "node_id":
                            int(node.id),
                        "error":
                            "quota_sync_failed",
                    })

            except Exception as exc:

                failed.append({
                    "subscription_id":
                        subscription_id,
                    "protocol":
                        "quota",
                    "node_id":
                        int(node.id),
                    "error":
                        str(exc)[:800],
                })

    return {
        "ok":
            len(failed) == 0,

        "node_id":
            int(node.id),

        "node_type":
            node_type,

        "membership_added":
            membership_added,

        "compatibility_updated":
            compatibility_updated,

        "active_subscriptions":
            len(active_ids),

        "provisioned_pairs":
            provisioned_pairs,

        "reused_pairs":
            reused_pairs,

        "failed":
            failed,
    }



@router.post("/{subscription_id}/provision-account")
async def provision_account(subscription_id:int, db:Session=Depends(get_db)):
    sub=db.get(Subscription,subscription_id)
    if not sub: raise HTTPException(status_code=404,detail="اشتراک پیدا نشد")
    user=db.get(User,sub.user_id)
    if not user: raise HTTPException(status_code=404,detail="کاربر پیدا نشد")
    # TWINPANEL_ACCOUNT_EXIT_ONLY_V1
    nodes = [
        node
        for node in _nodes(db, sub)
        if node.node_type == NodeType.EXIT
    ]
    protocols = _protocols(db, sub)

    if not nodes:
        raise HTTPException(
            status_code=409,
            detail="برای این اشتراک هیچ سرور خروجی معتبری انتخاب نشده است",
        )
    if not protocols: raise HTTPException(status_code=409,detail="برای اشتراک پروتکلی انتخاب نشده است")

    username = sub.account_username or _safe_username(sub, user)

    # TWINPANEL_PERSIST_ACCOUNT_USERNAME_V1
    if not sub.account_username:
        sub.account_username = username
    password = sub.account_password_encrypted or _numeric_secret(8)
    xray_id=str(uuid.uuid4())
    results=[]; errors=[]
    field_map={"cisco":"enable_cisco","openvpn":"enable_openvpn","wireguard":"enable_wireguard","l2tp":"enable_l2tp","v2ray":"enable_v2ray"}

    for protocol in protocols:
        protocol_items=[]
        for node in nodes:
            if not bool(getattr(node,field_map[protocol],False)):
                continue
            try:
                if protocol=="cisco": item=await _cisco(db,node,sub,user,username,password)
                elif protocol=="openvpn": item=await _openvpn(db,node,sub,user)
                elif protocol=="wireguard": item=await _wireguard(db,node,sub,user)
                elif protocol=="l2tp": item=await _l2tp(db,node,sub,user,username,password)
                elif protocol=="v2ray": item=await _xray(db,node,sub,user,xray_id)
                else: continue
                protocol_items.append(item)
            except Exception as exc:
                errors.append({"protocol":protocol,"node":node.name,"error":str(exc)})
        if protocol_items:
            cred=db.query(ProtocolCredential).filter(ProtocolCredential.subscription_id==sub.id,ProtocolCredential.protocol==protocol).first()
            if not cred:
                cred=ProtocolCredential(subscription_id=sub.id,protocol=protocol); db.add(cred)
            cred.username=username if protocol in {"cisco","l2tp"} else None
            cred.secret_encrypted=_enc({"password":password}) if protocol in {"cisco","l2tp"} else None
            cred.config_text_encrypted=_enc(protocol_items); cred.is_active=True
            results.append({"protocol":protocol,"username":cred.username,"items":protocol_items})
    db.commit()

    # TWINPANEL_AUTO_QUOTA_AFTER_ACCOUNT_PROVISION_V1
    quota_sync = {
        "ok": True,
        "nodes": [],
    }

    if results:
        from ..services.quota_refresh import (
            sync_subscription_quota_nodes,
        )

        quota_sync = (
            await sync_subscription_quota_nodes(
                db,
                sub.id,
            )
        )

        if not quota_sync.get("ok"):
            errors.append({
                "protocol": "quota",
                "node": "quota-agent",
                "error":
                    "Quota Agent sync failed",
            })

    if not results:
        raise HTTPException(status_code=502,detail={"message":"هیچ اکانتی روی سرورها ساخته نشد","errors":errors})
    payload = _public_payload(db, sub)
    payload.update({
        "ok": len(errors) == 0,
        "errors": errors,
        "quota": quota_sync,
        "generated_at":
            datetime.utcnow().isoformat() + "Z",
    })
    return payload


@router.post("/{subscription_id}/refresh-simple-passwords")
async def refresh_simple_passwords(subscription_id: int, db: Session = Depends(get_db)):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")

    user = db.get(User, sub.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    selected_protocols = set(_protocols(db, sub))
    target_protocols = [p for p in ("cisco", "l2tp") if p in selected_protocols]
    if not target_protocols:
        raise HTTPException(status_code=409, detail="این اشتراک Cisco یا L2TP ندارد")

    nodes = [
        node
        for node in _nodes(db, sub)
        if node.node_type == NodeType.EXIT
    ]

    if not nodes:
        raise HTTPException(
            status_code=409,
            detail="برای این اشتراک هیچ سرور خروجی معتبری انتخاب نشده است",
        )

    username = sub.account_username or _safe_username(sub, user)
    password = sub.account_password_encrypted or _numeric_secret(8)
    results = []
    errors = []

    for protocol in target_protocols:
        items = []
        flag = "enable_cisco" if protocol == "cisco" else "enable_l2tp"
        for node in nodes:
            if not bool(getattr(node, flag, False)):
                continue
            try:
                if protocol == "cisco":
                    item = await _cisco(db, node, sub, user, username, password)
                else:
                    item = await _l2tp(db, node, sub, user, username, password)
                items.append(item)
            except Exception as exc:
                errors.append({"protocol": protocol, "node": node.name, "error": str(exc)})

        if items:
            cred = (
                db.query(ProtocolCredential)
                .filter(
                    ProtocolCredential.subscription_id == sub.id,
                    ProtocolCredential.protocol == protocol,
                )
                .first()
            )
            if not cred:
                cred = ProtocolCredential(subscription_id=sub.id, protocol=protocol)
                db.add(cred)
            cred.username = username
            cred.secret_encrypted = _enc({"password": password})
            cred.config_text_encrypted = _enc(items)
            cred.is_active = True
            results.append({"protocol": protocol, "username": username, "items": items})

    db.commit()

    if not results:
        raise HTTPException(
            status_code=502,
            detail={"message": "بازسازی Cisco/L2TP ناموفق بود", "errors": errors},
        )

    payload = _public_payload(db, sub)
    payload.update(
        {
            "ok": len(errors) == 0,
            "new_numeric_password": password,
            "updated_protocols": [r["protocol"] for r in results],
            "errors": errors,
        }
    )
    return payload



@router.get("/node-domains")
def node_domains(db: Session = Depends(get_db)):
    rows = db.query(Node).filter(Node.retired_at.is_(None)).order_by(Node.id.asc()).all()
    return {
        "ok": True,
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "public_ip": n.public_ip,
                "public_domain": n.public_domain,
                "effective_host": _node_host(n),
            }
            for n in rows
        ],
    }


@router.put("/node-domains/{node_id}")
def update_node_domain(node_id: int, payload: dict[str, Any], db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    domain = str(payload.get("domain") or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/")[0].strip()
    if ":" in domain:
        domain = domain.split(":", 1)[0]

    if not domain or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain):
        raise HTTPException(status_code=422, detail="دامنه معتبر نیست")

    node.public_domain = domain
    db.commit()
    db.refresh(node)
    return {
        "ok": True,
        "node_id": node.id,
        "name": node.name,
        "public_ip": node.public_ip,
        "public_domain": node.public_domain,
        "message": "دامنه سرور ذخیره شد. برای اعمال روی کانفیگ‌های قبلی، اکانت را دوباره Provision کنید.",
    }



def _usage_payload(db: Session, sub: Subscription) -> dict[str, Any]:
    total = max(int(sub.traffic_limit_bytes or 0), 0)
    used = max(int(sub.traffic_used_bytes or 0), 0)
    unlimited = total <= 0
    remaining = None if unlimited else max(total - used, 0)
    percent = 0.0 if unlimited else min(100.0, (used / total * 100.0) if total else 0.0)
    last_event = db.query(func.max(QuotaUsageEvent.created_at)).filter(QuotaUsageEvent.subscription_id == sub.id).scalar()
    gib = 1024 ** 3
    return {
        "subscription_id": sub.id,
        "used_bytes": used,
        "total_bytes": total,
        "remaining_bytes": remaining,
        "used_gb": round(used / gib, 2),
        "total_gb": None if unlimited else round(total / gib, 2),
        "remaining_gb": None if unlimited else round(remaining / gib, 2),
        "percent": round(percent, 1),
        "unlimited": unlimited,
        "last_usage_event_at": last_event.isoformat() + "Z" if last_event else None,
        "refreshed_at": datetime.utcnow().isoformat() + "Z",
    }


@public_router.get("/{token}/usage")
def public_usage(token: str, db: Session = Depends(get_db)):
    sub = _subscription_from_share_token(token, db)
    return _usage_payload(db, sub)


def _h(value: Any) -> str:
    return html.escape("" if value is None else str(value))




def _credential_sections(payload: dict[str, Any], token: str) -> str:
    meta = {
        "cisco": ("Cisco AnyConnect", "OpenConnect", "C", "cisco"),
        "openvpn": ("OpenVPN", "فایل آماده", "O", "openvpn"),
        "wireguard": ("WireGuard", "QR + فایل", "W", "wireguard"),
        "l2tp": ("L2TP / IPsec", "IPsec", "L2TP", "l2tp"),
        "v2ray": ("V2Ray", "QR + لینک", "V", "v2ray"),
    }
    tabs = []
    panes = []
    creds = payload.get("credentials", [])

    for idx, cred in enumerate(creds):
        protocol = cred.get("protocol", "")
        label, sublabel, symbol, css = meta.get(protocol, (protocol, "اتصال", "•", "default"))
        active = " active" if idx == 0 else ""

        tabs.append(
            '<button class="proto-card %s%s" type="button" data-tab="%s">'
            '<span class="proto-selected">✓</span>'
            '<span class="proto-logo">%s</span>'
            '<b>%s</b><small>%s</small><em>فعال</em></button>'
            % (css, active, _h(protocol), _h(symbol), _h(label), _h(sublabel))
        )

        nodes_html = []
        server_tabs = []
        for item_idx, item in enumerate(cred.get("items", [])):
            node_id = int(item.get("node_id") or 0)
            server = _h(item.get("server") or "")
            node_name = _h(item.get("node") or "سرور")
            port = _h(item.get("port") or item.get("ports") or "")
            username = _h(item.get("username") or "")
            password = _h(item.get("password") or "")
            psk = _h(item.get("psk") or "")
            uuid_value = _h(item.get("uuid") or "")
            uri = _h(item.get("uri") or "")

            details = []

            def add_card(icon_class, icon, title, value, copy=True, good=False, note=""):
                if not value:
                    return
                copy_html = f'<button type="button" data-copy="{value}">کپی</button>' if copy else ""
                good_cls = " good" if good else ""
                note_html = f"<i>{_h(note)}</i>" if note else ""
                details.append(
                    f'<div class="detail-item"><span class="detail-icon {icon_class}">{icon}</span>'
                    f'<div><small>{_h(title)}</small><b class="{good_cls}" dir="ltr">{value}</b>{note_html}</div>{copy_html}</div>'
                )

            # TWINPANEL_CONNECTION_UI_V1
            if protocol == "cisco":
                cisco_endpoint = (
                    f"{server}:{port}"
                    if port
                    else server
                )
                add_card(
                    "blue",
                    "◎",
                    "Server & Port",
                    cisco_endpoint,
                )

            elif protocol == "l2tp":
                add_card(
                    "blue",
                    "◎",
                    "Server",
                    server,
                )

            add_card(
                "cyan",
                "●",
                "Username",
                username,
            )

            add_card(
                "green",
                "▣",
                "Password",
                password,
                True,
                True,
            )

            add_card(
                "teal",
                "◆",
                "IPsec Secret",
                psk,
                True,
                True,
            )

            action = ""
            if protocol == "openvpn" and item.get("config"):
                action = (
                    '<div class="delivery-action">'
                    '<div class="file-row"><span class="file-badge">OVPN</span><div><b>فایل OpenVPN آماده است</b>'
                    '<small>فایل را دانلود و داخل OpenVPN Connect وارد کنید.</small></div></div>'
                    f'<a class="download-action orange" href="/v1/connect/{_h(token)}/file/openvpn/{node_id}">دانلود فایل .ovpn</a>'
                    '</div>'
                )
            elif protocol == "wireguard" and item.get("config"):
                action = (
                    '<div class="delivery-action qr-action">'
                    f'<img src="{_h(item.get("qr"))}" alt="WireGuard QR">'
                    '<div><b>اتصال سریع WireGuard</b><small>QR را اسکن کنید یا فایل کانفیگ را دانلود کنید.</small>'
                    f'<a class="download-action rose" href="/v1/connect/{_h(token)}/file/wireguard/{node_id}">دانلود فایل .conf</a></div></div>'
                )
            elif protocol == "v2ray" and uri:
                action = (
                    '<div class="delivery-action qr-action">'
                    f'<img src="{_h(item.get("qr"))}" alt="V2Ray QR">'
                    '<div><b>اتصال سریع V2Ray</b><small>QR را در Hiddify یا v2rayN اسکن کنید.</small>'
                    f'<button class="download-action violet" type="button" data-copy="{uri}">کپی لینک اتصال</button></div></div>'
                    f'<details class="technical"><summary>نمایش لینک کامل</summary><code>{uri}</code></details>'
                )

            endpoint_html = (
                ""
                if protocol in {"cisco", "l2tp"}
                else '<em>کانفیگ آماده</em>'
            )
            server_active = " active" if item_idx == 0 else ""
            server_tabs.append(
                f'<button class="server-chip{server_active}" type="button" data-server-index="{item_idx}"><i></i>{node_name}</button>'
            )
            nodes_html.append(
                f'<article class="node-block server-panel{server_active}" data-server-index="{item_idx}">'
                f'<div class="node-title"><span><i></i><b>{node_name}</b></span>{endpoint_html}</div>'
                f'<div class="details-grid" style="--detail-cols:{len(details)}">{"".join(details)}</div>{action}</article>'
            )

        panes.append(
            f'<section class="proto-pane{active}" data-pane="{_h(protocol)}">'
            f'<div class="details-title"><span><strong>{_h(label)}</strong><small>جزئیات اتصال</small></span>'
            f'<i class="pane-symbol {css}">{_h(symbol)}</i></div>'
            f'<div class="server-switcher">{"".join(server_tabs)}</div>'
            f'<div class="server-panels">{"".join(nodes_html)}</div></section>'
        )

    if not tabs:
        return '<section class="empty-state"><b>هنوز اطلاعات اتصال ساخته نشده است.</b><small>از پنل مدیریت Provision Account را اجرا کنید.</small></section>'

    return (
        '<section class="protocol-section">'
        '<div class="section-heading"><span><small>پروتکل‌های فعال</small><h2>انتخاب پروتکل</h2>'
        '<p>یک پروتکل را انتخاب کنید تا فقط اطلاعات همان نمایش داده شود.</p></span><i>☷</i></div>'
        f'<div class="protocol-grid">{"".join(tabs)}</div>'
        f'<div class="protocol-content">{"".join(panes)}</div>'
        '</section>'
    )


# TWINPANEL_FEATURED_APPS_V1
def _featured_apps_html(
    downloads: dict[str, Any]
) -> str:
    platforms = [
        ("android", "Android"),
        ("ios", "iOS"),
        ("windows", "Windows"),
        ("macos", "macOS"),
    ]

    output = []

    for os_key, os_label in platforms:
        apps = downloads.get(os_key) or []

        links = []

        for app in apps:
            name = _h(
                app.get("name")
                or "App"
            )

            url = _h(
                app.get("url")
                or "#"
            )

            links.append(
                f'<a class="platform-app" '
                f'href="{url}" '
                f'target="_blank" '
                f'rel="noreferrer">'
                f'{name}</a>'
            )

        if not links:
            links.append(
                '<span class="platform-app disabled">'
                'No app'
                '</span>'
            )

        output.append(
            f'<div class="platform {os_key}">'
            f'<strong>{_h(os_label)}</strong>'
            f'<span class="platform-apps">'
            f'{"".join(links)}'
            f'</span>'
            f'</div>'
        )

    return "".join(output)


# TWINPANEL_SMART_DOWNLOADS_V2
def _smart_apps_html(
    downloads: dict[str, Any]
) -> str:

    systems = [
        ("windows", "Windows", "W"),
        ("macos", "macOS", "M"),
        ("android", "Android", "A"),
        ("ios", "iPhone / iPad", "i"),
        ("linux", "Linux", "L"),
    ]

    selectors = []
    panels = []

    for key, label, symbol in systems:
        apps = downloads.get(key) or []

        if not apps:
            continue

        selectors.append(
            f'<button type="button" '
            f'class="smart-os-card" '
            f'data-app-os="{_h(key)}">'
            f'<span>{_h(symbol)}</span>'
            f'<b>{_h(label)}</b>'
            f'<small>{len(apps)} Apps</small>'
            f'</button>'
        )

        app_cards = []

        for app in apps:
            name = _h(
                app.get("name")
                or "App"
            )

            url = _h(
                app.get("url")
                or "#"
            )

            initial = _h(
                str(
                    app.get("name")
                    or "A"
                )[:1].upper()
            )

            note = _h(
                app.get("note")
                or "دانلود برنامه"
            )

            app_cards.append(
                f'<a class="smart-download-app" '
                f'href="{url}" '
                f'target="_blank" '
                f'rel="noopener noreferrer">'
                f'<span class="smart-download-logo">'
                f'{initial}'
                f'</span>'
                f'<span class="smart-download-copy">'
                f'<b>{name}</b>'
                f'<small>{note}</small>'
                f'</span>'
                f'<span class="smart-download-arrow">'
                f'↗'
                f'</span>'
                f'</a>'
            )

        panels.append(
            f'<section class="smart-os-panel" '
            f'data-app-panel="{_h(key)}">'
            f'<div class="smart-os-title">'
            f'<b>{_h(label)}</b>'
            f'<small>برنامه‌های مناسب این سیستم</small>'
            f'</div>'
            f'<div class="smart-download-grid">'
            f'{"".join(app_cards)}'
            f'</div>'
            f'</section>'
        )

    if not selectors:
        return (
            '<div class="empty-state">'
            '<b>برنامه‌ای برای دانلود ثبت نشده است.</b>'
            '</div>'
        )

    return (
        '<div class="smart-downloads">'
        '<div class="smart-os-selector">'
        + "".join(selectors) +
        '</div>'
        '<div class="smart-os-panels">'
        + "".join(panels) +
        '</div>'
        '</div>'
    )


def _apps_html(downloads: dict[str, Any]) -> str:
    os_labels={"windows":"Windows","macos":"macOS","android":"Android","ios":"iPhone / iPad","linux":"Linux"}
    out=[]
    for os_key, apps in downloads.items():
        links="".join(f'<a href="{_h(a.get("url"))}" target="_blank" rel="noreferrer">{_h(a.get("name"))}</a>' for a in apps)
        out.append(f'<div class="os"><b>{os_labels.get(os_key,os_key)}</b><span>{links}</span></div>')
    return "".join(out)




@public_router.get("/{token}/qr")
def subscription_qr(token: str, db: Session = Depends(get_db)):
    import io
    import qrcode
    from fastapi.responses import Response

    sub = None

    try:
        sub = _subscription_from_share_token(token, db)
    except Exception:
        pass

    if not sub:
        return Response(status_code=404)

    url = _share_url(db, sub)

    img = qrcode.make(url)

    buf = io.BytesIO()
    img.save(buf, format="PNG")

    return Response(
        content=buf.getvalue(),
        media_type="image/png"
    )


@public_router.get("/{token}", response_class=HTMLResponse)
def public_connection_page(token: str, db: Session = Depends(get_db)):
    from ..branding_models import BrandingSettings

    sub = _subscription_from_share_token(token, db)

    if str(sub.status.value if hasattr(sub.status, "value") else sub.status) != "active":
        return HTMLResponse(
            """
            <html dir="rtl">
            <head>
            <title>اشتراک غیر فعال</title>
            <style>
            body{
                background:#08090d;
                color:#fff;
                font-family:tahoma;
                display:flex;
                align-items:center;
                justify-content:center;
                height:100vh;
            }
            .box{
                background:#111827;
                padding:40px;
                border-radius:20px;
                text-align:center;
            }
            h1{color:#ef4444}
            </style>
            </head>
            <body>
            <div class="box">
            <h1>اشتراک غیر فعال است</h1>
            <p>این اشتراک در حال حاضر فعال نیست.</p>
            </div>
            </body>
            </html>
            """
        )

    payload = _public_payload(db, sub)
    usage = _usage_payload(db, sub)
    user = db.get(User, sub.user_id)

    # TWINPANEL_PUBLIC_BRANDING_V4
    branding = db.query(
        BrandingSettings
    ).first()

    brand_name = str(
        getattr(
            branding,
            "brand_name",
            None,
        )
        or "Twin Panel"
    ).strip() or "Twin Panel"

    site_title = str(
        getattr(
            branding,
            "site_title",
            None,
        )
        or brand_name
    ).strip() or brand_name

    brand_mark = next(
        (
            ch.upper()
            for ch in brand_name
            if not ch.isspace()
        ),
        "T",
    )

    # TWINPANEL_CONNECT_THEME_V1
    def safe_brand_color(value: Any, fallback: str) -> str:
        value = str(value or "").strip()

        if re.fullmatch(
            r"#[0-9A-Fa-f]{6}",
            value,
        ):
            return value

        return fallback

    primary_color = safe_brand_color(
        getattr(
            branding,
            "primary_color",
            None,
        ),
        "#7C3AED",
    )

    secondary_color = safe_brand_color(
        getattr(
            branding,
            "secondary_color",
            None,
        ),
        "#4F46E5",
    )

    title = f"MV-{sub.id}"
    starts = sub.starts_at.strftime("%Y/%m/%d") if sub.starts_at else "—"
    expires = sub.expires_at.strftime("%Y/%m/%d") if sub.expires_at else "—"
    user_name = user.full_name if user and user.full_name else user.email if user else "کاربر"
    status_value = getattr(
        sub.status,
        "value",
        str(sub.status),
    )

    if status_value == "active":
        body = _credential_sections(payload, token)
    else:
        body = """
        <div class="inactive-subscription">
            <h2>اشتراک غیر فعال است</h2>
            <p>این اشتراک در حال حاضر فعال نیست.</p>
        </div>
        """

    # TWINPANEL_LOCAL_APP_DOWNLOADS_V1
    # Keep every app already returned by the API and append
    # TwinPanel-hosted installers without changing the subscription payload.
    raw_downloads = payload.get("downloads") or {}

    downloads = (
        {
            key: list(value or [])
            for key, value in raw_downloads.items()
        }
        if isinstance(raw_downloads, dict)
        else {}
    )

    local_downloads = {
        # TWINPANEL_ANDROID_MACOS_DIRECT_APPS_V1
        "android": [
            {
                "name": "Cisco Secure Client · Android",
                "note": "دانلود مستقیم از TwinPanel · AnyConnect VPN",
                "url": (
                    "/downloads/apps/android/cisco/"
                    "Cisco-Secure-Client-Android.apk"
                ),
            },
            {
                "name": "OpenVPN for Android",
                "note": "دانلود مستقیم از TwinPanel · OpenVPN",
                "url": (
                    "/downloads/apps/android/openvpn/"
                    "OpenVPN-for-Android.apk"
                ),
            },
            {
                "name": "WireGuard · Android",
                "note": "دانلود مستقیم از TwinPanel",
                "url": (
                    "/downloads/apps/android/wireguard/"
                    "WireGuard-Android.apk"
                ),
            },
            {
                "name": "v2rayNG · Android 64-bit",
                "note": "دانلود مستقیم از TwinPanel · V2Ray / Xray",
                "url": (
                    "/downloads/apps/android/v2rayng/"
                    "v2rayNG-android-arm64.apk"
                ),
            },
            {
                "name": "OpenConnect 1.12 · Android",
                "note": "دانلود مستقیم از TwinPanel · Cisco / OpenConnect",
                "url": (
                    "/downloads/apps/android/openconnect/"
                    "OpenConnect-1.12-Android.apk"
                ),
            },
        ],
        "windows": [
            {
                "name": "Cisco Secure Client · Windows",
                "note": "دانلود مستقیم از TwinPanel · AnyConnect VPN",
                "url": (
                    "/downloads/apps/windows/cisco/"
                    "Cisco-Secure-Client-Windows.msi"
                ),
            },
            {
                "name": "v2rayN 7.24.8 · Windows 64",
                "note": "دانلود مستقیم از TwinPanel",
                "url": (
                    "/downloads/apps/windows/v2rayn/"
                    "v2rayN-windows-64-desktop.zip"
                ),
            },
            {
                "name": "WireGuard · Windows 64-bit",
                "note": "دانلود مستقیم از TwinPanel",
                "url": (
                    "/downloads/apps/windows/wireguard/"
                    "WireGuard-Windows-amd64.msi"
                ),
            },
            {
                "name": "OpenVPN Community 2.7.6 · Windows 64-bit",
                "note": "دانلود مستقیم از TwinPanel",
                "url": (
                    "/downloads/apps/windows/openvpn/"
                    "OpenVPN-2.7.6-Windows-amd64.msi"
                ),
            },
        ],
        "macos": [
            {
                "name": "Cisco Secure Client · macOS",
                "note": "دانلود مستقیم از TwinPanel · AnyConnect VPN",
                "url": (
                    "/downloads/apps/macos/cisco/"
                    "Cisco-Secure-Client-macOS.dmg"
                ),
            },
            {
                "name": "OpenVPN Connect · macOS",
                "note": "دانلود مستقیم از TwinPanel · OpenVPN",
                "url": (
                    "/downloads/apps/macos/openvpn/"
                    "OpenVPN-Connect-macOS.dmg"
                ),
            },
            {
                "name": "WireGuard · macOS",
                "note": "دریافت از Mac App Store",
                "url": (
                    "https://apps.apple.com/us/app/"
                    "wireguard/id1451685025?mt=12"
                ),
            },
            {
                "name": "v2rayN 7.24.8 · macOS Apple Silicon",
                "note": "دانلود مستقیم از TwinPanel · M1 / M2 / M3 / M4",
                "url": (
                    "/downloads/apps/macos/v2rayn/"
                    "v2rayN-macos-arm64.dmg"
                ),
            },
            {
                "name": "v2rayN 7.24.8 · macOS Intel",
                "note": "دانلود مستقیم از TwinPanel · Intel",
                "url": (
                    "/downloads/apps/macos/v2rayn/"
                    "v2rayN-macos-intel.dmg"
                ),
            },
        ],
        # TWINPANEL_IOS_COMPLETE_APPS_V1
        "ios": [
            {
                "name": "Cisco Secure Client · iPhone / iPad",
                "note": "دریافت از App Store · AnyConnect VPN",
                "url": (
                    "https://apps.apple.com/us/app/"
                    "cisco-secure-client/id1135064690"
                ),
            },
            {
                "name": "OpenVPN Connect · iPhone / iPad",
                "note": "دریافت از App Store · OpenVPN",
                "url": (
                    "https://apps.apple.com/us/app/"
                    "openvpn-connect/id590379981"
                ),
            },
            {
                "name": "WireGuard · iPhone / iPad",
                "note": "دریافت از App Store · WireGuard",
                "url": (
                    "https://apps.apple.com/us/app/"
                    "wireguard/id1441195209"
                ),
            },
            {
                "name": "Streisand · iPhone / iPad",
                "note": "دریافت از App Store · V2Ray / Xray",
                "url": (
                    "https://apps.apple.com/us/app/"
                    "streisand/id6450534064"
                ),
            },
            {
                "name": "L2TP · iPhone / iPad",
                "note": "بدون نیاز به نصب برنامه · آموزش اتصال",
                "url": (shop_base_url(db) or "") + "/#guides",
            },
        ],
        "linux": [
            {
                "name": "WireGuard · Linux",
                "note": "روش نصب رسمی",
                "url": "https://www.wireguard.com/install/",
            },
            {
                "name": "OpenVPN · Linux",
                "note": "روش نصب رسمی",
                "url": "https://openvpn.net/community-downloads/",
            },
            {
                "name": "OpenConnect · Linux",
                "note": "روش نصب رسمی",
                "url": "https://www.infradead.org/openconnect/download.html",
            },
            {
                "name": "v2rayN 7.24.8 · amd64",
                "note": "دانلود مستقیم از TwinPanel",
                "url": (
                    "/downloads/apps/linux/v2rayn/"
                    "v2rayN-linux-amd64.deb"
                ),
            },
            {
                "name": "v2rayN 7.24.8 · arm64",
                "note": "دانلود مستقیم از TwinPanel",
                "url": (
                    "/downloads/apps/linux/v2rayn/"
                    "v2rayN-linux-arm64.deb"
                ),
            },
        ],
    }

    for os_key, apps in local_downloads.items():
        current = downloads.setdefault(os_key, [])

        existing_urls = {
            str(item.get("url") or "")
            for item in current
            if isinstance(item, dict)
        }

        for app in apps:
            if app["url"] not in existing_urls:
                current.append(app)
                existing_urls.add(app["url"])

    smart_apps = _smart_apps_html(downloads)

    used = float(usage.get("used_gb") or 0)
    pct = float(usage.get("percent") or 0)
    total_label = "نامحدود" if usage["unlimited"] else f'{float(usage.get("total_gb") or 0):.1f} GB'
    remaining_label = "∞" if usage["unlimited"] else f'{float(usage.get("remaining_gb") or 0):.1f} GB'
    used_label = f"{used:.1f} GB"

    page = f'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#11195a">
<title>{_h(site_title)} - {_h(title)}</title>
<style>
:root{{--brand-primary:{primary_color};--brand-secondary:{secondary_color};--navy:#0d1b59;--purple:#7244ec;--pink:#e2289c;--blue:#287cf5;--cyan:#12bfe4;--green:#20b86a;--orange:#ff8a25;--rose:#e94a65;--ink:#15203c;--muted:#71809f;--line:#dfe8f6;--page:#f7f9fd}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#fff 0,#f8faff 100%);color:var(--ink);font-family:Tahoma,Arial,sans-serif;-webkit-font-smoothing:antialiased}}button,a{{font:inherit}}button{{cursor:pointer}}
.topnav{{height:82px;background:linear-gradient(110deg,var(--brand-secondary) 0%,#171663 52%,var(--brand-primary) 100%);color:#fff}}
.topnav-inner{{width:min(1460px,95vw);height:100%;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:24px}}
.brand{{display:flex;align-items:center;gap:11px;direction:ltr}}
.theme-toggle{{width:38px;height:38px;border:1px solid rgba(255,255,255,.22);border-radius:12px;background:rgba(255,255,255,.12);color:#fff;display:grid;place-items:center;font-size:17px;transition:.18s;backdrop-filter:blur(8px)}}
.theme-toggle:hover{{background:rgba(255,255,255,.22);transform:translateY(-1px)}}

html[data-theme="dark"]{{color-scheme:dark}}
html[data-theme="dark"] body{{background:linear-gradient(180deg,#090d18 0%,#0d1221 100%);color:#edf2ff}}

html[data-theme="dark"] .shell{{color:#edf2ff}}

html[data-theme="dark"] .proto-card,
html[data-theme="dark"] .proto-pane,
html[data-theme="dark"] .detail-item,
html[data-theme="dark"] .delivery-action,
html[data-theme="dark"] .download-panel,
html[data-theme="dark"] .smart-os-card,
html[data-theme="dark"] .smart-download-app{{
background:#12192b;
border-color:#293555;
color:#eef3ff;
}}

html[data-theme="dark"] .proto-pane{{
background:#0f1728;
box-shadow:0 8px 28px rgba(0,0,0,.18);
}}

html[data-theme="dark"] .details-title,
html[data-theme="dark"] .node-block,
html[data-theme="dark"] .smart-os-panel{{
border-color:#26324e;
}}

html[data-theme="dark"] .section-heading h2,
html[data-theme="dark"] .details-title strong,
html[data-theme="dark"] .panel-title b,
html[data-theme="dark"] .smart-os-title>b{{
color:#c7d8ff;
}}

html[data-theme="dark"] .section-heading p,
html[data-theme="dark"] .details-title small,
html[data-theme="dark"] .node-title em,
html[data-theme="dark"] .detail-item small,
html[data-theme="dark"] .smart-os-title>small,
html[data-theme="dark"] .smart-download-copy>small,
html[data-theme="dark"] .smart-os-card>small{{
color:#8493b2;
}}

html[data-theme="dark"] .detail-item{{
background:#151e32;
}}

html[data-theme="dark"] .smart-os-card.active{{
background:linear-gradient(135deg,rgba(124,58,237,.22),rgba(79,70,229,.15));
border-color:var(--brand-primary);
box-shadow:0 8px 25px rgba(73,53,190,.18);
}}

html[data-theme="dark"] .smart-download-app:hover,
html[data-theme="dark"] .proto-card:hover{{
border-color:#6659d9;
}}

html[data-theme="dark"] .download-panel{{
box-shadow:0 10px 35px rgba(0,0,0,.13);
}}

html[data-theme="dark"] .footer{{
background:#11192b;
color:#8190ae;
border:1px solid #202b45;
}}

html[data-theme="dark"] .empty-state{{
background:#11192b;
border-color:#34415f;
color:#e8eeff;
}}

html[data-theme="dark"] .technical code{{
background:#0b1120;
color:#c7d6fa;
}}

html[data-theme="dark"] .section-heading>i{{
background:#191c38;
color:#9d8aff;
}}

html[data-theme="dark"] .detail-item button{{
background:#1a2948;
color:#79aaff;
}}

html[data-theme="dark"] .smart-os-card>span{{
background:#1b2540;
color:#9d8dff;
}}

html[data-theme="dark"] .smart-os-card.active>span{{
background:linear-gradient(135deg,var(--brand-primary),var(--brand-secondary));
color:#fff;
}}

html[data-theme="dark"] .smart-download-logo{{
background:linear-gradient(135deg,var(--brand-primary),var(--brand-secondary));
}}

body,
.proto-card,
.proto-pane,
.detail-item,
.download-panel,
.smart-os-card,
.smart-download-app,
.footer{{
transition:background .2s,border-color .2s,color .2s,box-shadow .2s;
}}.brand-mark{{width:42px;height:42px;display:grid;place-items:center;border-radius:13px;background:linear-gradient(135deg,#3868ff,#9a38f2);font:900 19px Arial;box-shadow:0 8px 24px rgba(119,69,240,.35)}}.brand b{{font:900 23px Arial}}
.account-head{{display:flex;align-items:center;gap:18px}}.online-badge{{display:flex;align-items:center;gap:6px;padding:7px 11px;border-radius:999px;background:rgba(199,47,229,.22);font-size:9px;font-weight:900}}.online-badge i{{width:7px;height:7px;border-radius:50%;background:#34d990}}.account-copy{{display:grid;grid-template-columns:auto auto;column-gap:22px;row-gap:3px}}.account-copy b{{font-size:13px}}.account-copy small{{font-size:8px;color:rgba(255,255,255,.68)}}.avatar{{width:43px;height:43px;display:grid;place-items:center;border-radius:50%;background:linear-gradient(135deg,#8c55ef,#6a49f5);font:900 15px Arial}}
.shell{{width:min(1460px,95vw);margin:auto;padding:28px 0 38px}}
.traffic-card{{display:grid;grid-template-columns:240px 1fr;gap:28px;align-items:center;padding:25px 30px;border-radius:22px;color:#fff;background:linear-gradient(115deg,var(--brand-secondary) 0%,var(--brand-primary) 48%,#e31c9a 100%);box-shadow:0 14px 34px rgba(91,42,178,.24)}}
.traffic-donut{{position:relative;width:175px;height:175px;display:grid;place-items:center;margin:auto;border-radius:50%;background:conic-gradient(#ff9b38 0 7%,#0fc8e5 7% {pct}%,rgba(255,255,255,.16) {pct}% 100%)}}.traffic-donut:before{{content:"";position:absolute;width:137px;height:137px;border-radius:50%;background:#3523a4}}.traffic-donut span{{position:relative;z-index:1;text-align:center}}.traffic-donut b{{display:block;font:900 38px Arial}}.traffic-donut small{{font-size:9px;color:rgba(255,255,255,.78)}}
.traffic-title{{display:flex;align-items:center;gap:10px;margin-bottom:22px}}.traffic-title h2{{font-size:20px;margin:0}}.live{{padding:7px 11px;border-radius:999px;background:linear-gradient(135deg,#15b1bd,#36c89b);font-size:9px;font-weight:900}}.traffic-stats{{display:grid;grid-template-columns:repeat(4,1fr)}}.traffic-stat{{min-height:78px;padding:4px 28px;border-left:1px solid rgba(255,255,255,.32);display:flex;flex-direction:column;justify-content:center}}.traffic-stat:last-child{{border-left:0}}.traffic-stat small{{font-size:10px;color:rgba(255,255,255,.78)}}.traffic-stat b{{font-size:27px;margin-top:7px;direction:ltr;text-align:right}}.traffic-stat.time b{{font-size:19px;direction:rtl}}.progress{{height:11px;margin-top:21px;border-radius:999px;overflow:hidden;background:rgba(60,0,90,.32);direction:ltr}}.progress i{{display:block;height:100%;width:{pct}%;border-radius:999px;background:linear-gradient(90deg,#2c7df6,#13c6e3,#8345ed,#ff8f3f);transition:width .4s}}
.section-heading{{display:flex;align-items:center;justify-content:space-between;margin:25px 2px 12px}}.section-heading span{{display:grid;gap:3px}}.section-heading small{{font-size:8px;color:#744ae8;font-weight:900}}.section-heading h2{{font-size:20px;margin:0;color:#16417b}}.section-heading p{{font-size:9px;color:var(--muted);margin:0}}.section-heading>i{{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;background:#f1edff;color:#7048ef;font-style:normal;font-size:19px}}
.protocol-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:22px}}.proto-card{{position:relative;min-height:145px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:0 6px 20px rgba(33,58,108,.045);transition:.18s;color:var(--ink)}}.proto-card:hover{{transform:translateY(-2px)}}.proto-logo{{width:57px;height:57px;display:grid;place-items:center;border-radius:50%;font:900 16px Arial;color:#fff}}.proto-card b{{font-size:12px}}.proto-card small{{font-size:8px;color:var(--muted)}}.proto-card em{{padding:5px 14px;border-radius:999px;font-size:8px;font-style:normal;font-weight:900}}.proto-selected{{display:none;position:absolute;top:12px;right:12px;width:22px;height:22px;place-items:center;border-radius:50%;color:#fff;font-size:9px}}.proto-card.active .proto-selected{{display:grid}}
.proto-card.cisco{{border-color:#9adefb}}.proto-card.cisco .proto-logo{{background:linear-gradient(135deg,#31c8e8,#1698c2)}}.proto-card.cisco em{{background:#dff7fd;color:#138bac}}.proto-card.cisco.active .proto-selected{{background:#2288dc}}.proto-card.openvpn{{border-color:#ffd5ac}}.proto-card.openvpn .proto-logo{{background:linear-gradient(135deg,#ff9f2f,#ee721c)}}.proto-card.openvpn em{{background:#fff0db;color:#e27718}}.proto-card.openvpn.active .proto-selected{{background:#ef7c1d}}.proto-card.wireguard{{border-color:#ffc6d1}}.proto-card.wireguard .proto-logo{{background:linear-gradient(135deg,#ec5f7a,#ca2d54)}}.proto-card.wireguard em{{background:#ffe4ea;color:#cf3457}}.proto-card.wireguard.active .proto-selected{{background:#dc3d62}}.proto-card.l2tp{{border-color:#ccecb8}}.proto-card.l2tp .proto-logo{{background:linear-gradient(135deg,#8bd636,#56b52a)}}.proto-card.l2tp em{{background:#e9f8db;color:#4da126}}.proto-card.l2tp.active .proto-selected{{background:#59b82d}}.proto-card.v2ray{{border-color:#d9c8ff}}.proto-card.v2ray .proto-logo{{background:linear-gradient(135deg,#9445ef,#6223d7)}}.proto-card.v2ray em{{background:#eee4ff;color:#6940d3}}.proto-card.v2ray.active .proto-selected{{background:#7042df}}
.proto-pane{{display:none;margin-top:14px;border:1px solid #bdd9ff;border-radius:16px;background:#fafdff;box-shadow:0 8px 28px rgba(34,79,143,.04);overflow:hidden}}.proto-pane.active{{display:block}}.details-title{{display:flex;align-items:center;justify-content:space-between;padding:15px 20px;border-bottom:1px solid #dce9f8}}.details-title span{{display:grid;gap:2px}}.details-title strong{{font-size:16px;color:#1553a0}}.details-title small{{font-size:8px;color:var(--muted)}}.pane-symbol{{width:34px;height:34px;display:grid;place-items:center;border-radius:10px;color:#fff;font:900 10px Arial;font-style:normal}}.pane-symbol.cisco{{background:#20add2}}.pane-symbol.openvpn{{background:#f28221}}.pane-symbol.wireguard{{background:#da4666}}.pane-symbol.l2tp{{background:#65bb31}}.pane-symbol.v2ray{{background:#7141df}}
.node-block{{padding:17px 20px;border-top:1px solid #e7eff8}}.node-block:first-of-type{{border-top:0}}.node-title{{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}}.node-title span{{display:flex;align-items:center;gap:7px}}.node-title i{{width:7px;height:7px;border-radius:50%;background:#25bc78}}.node-title b{{font-size:10px}}.node-title em{{font-size:9px;font-style:normal;color:var(--muted)}}
.details-grid{{display:grid;grid-template-columns:repeat(var(--detail-cols,6),1fr);gap:12px}}.detail-item{{min-height:118px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:8px;padding:13px 9px;border:1px solid #dbe7f7;border-radius:12px;background:#fff}}.detail-icon{{width:29px;height:29px;display:grid;place-items:center;border-radius:9px;font-style:normal;font-size:13px;font-weight:900}}.detail-icon.blue{{background:#e5f1ff;color:#1971dc}}.detail-icon.cyan{{background:#e2faff;color:#09a9d3}}.detail-icon.green{{background:#e9f8ef;color:#19a75e}}.detail-icon.indigo{{background:#e9efff;color:#355ac8}}.detail-icon.teal{{background:#e7faf5;color:#159873}}.detail-icon.violet{{background:#f0eaff;color:#7041da}}.detail-item div{{display:grid;gap:4px}}.detail-item small{{font-size:7px;color:#687d9d}}.detail-item b{{font-size:10px;max-width:100%;overflow:hidden;text-overflow:ellipsis}}.detail-item b.good{{color:#16a34a}}.detail-item i{{font-size:7px;font-style:normal;color:#16a34a;background:#dcf8e5;padding:3px 8px;border-radius:999px}}.detail-item button{{border:0;border-radius:999px;padding:6px 14px;background:#e7f0ff;color:#1766d3;font-size:8px;font-weight:900}}
.delivery-action{{margin-top:14px;padding:15px;border-radius:13px;border:1px solid #e4e9f3;background:#fff}}.file-row{{display:flex;align-items:center;gap:10px}}.file-badge{{width:55px;height:55px;display:grid;place-items:center;border-radius:13px;background:linear-gradient(135deg,#ff9d32,#eb701d);color:#fff;font:900 9px Arial}}.file-row div{{display:grid;gap:4px}}.delivery-action b{{font-size:11px}}.delivery-action small{{font-size:8px;color:var(--muted)}}.download-action{{display:flex;align-items:center;justify-content:center;margin-top:10px;min-height:42px;border:0;border-radius:10px;color:#fff;text-decoration:none;font-size:9px;font-weight:900;width:100%}}.download-action.orange{{background:linear-gradient(135deg,#ff932f,#e86a1b)}}.download-action.rose{{background:linear-gradient(135deg,#e95d79,#c93457)}}.download-action.violet{{background:linear-gradient(135deg,#8054ef,#5e2fd0)}}.qr-action{{display:grid;grid-template-columns:160px 1fr;align-items:center;gap:16px}}.qr-action>img{{width:150px;height:150px;padding:6px;border:1px solid #e1e7f1;border-radius:13px;background:#fff}}.qr-action>div{{display:grid;gap:5px}}.technical{{margin-top:8px;font-size:8px;color:var(--muted)}}.technical code{{display:block;margin-top:6px;padding:8px;border-radius:8px;background:#f2f4fb;direction:ltr;text-align:left;word-break:break-all;font-size:7px}}
.lower-grid{{display:grid;grid-template-columns:1fr;gap:16px;margin-top:16px}}
.smart-downloads{{display:grid;gap:16px}}
.smart-os-selector{{display:none}}
.smart-os-card{{min-height:84px;border:1px solid #dfe7f5;border-radius:13px;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;color:#1d2944;transition:.18s}}
.smart-os-card:hover{{transform:translateY(-2px);border-color:#9dbbf0}}
.smart-os-card>span{{width:31px;height:31px;border-radius:9px;display:grid;place-items:center;background:#eef3ff;color:#5c4be2;font-size:11px;font-weight:900}}
.smart-os-card>b{{font-size:10px}}
.smart-os-card>small{{font-size:7px;color:#8592a9}}
.smart-os-card.active{{border-color:#6954e9;background:linear-gradient(135deg,#f4f1ff,#eef6ff);box-shadow:0 7px 22px rgba(69,73,170,.12)}}
.smart-os-card.active>span{{background:linear-gradient(135deg,#7154ec,#3d86f1);color:#fff}}
.smart-os-panel{{display:none;border-top:1px solid #edf1f7;padding-top:14px}}
.smart-os-panel.active{{display:block}}
.smart-os-title{{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}}
.smart-os-title>b{{font-size:13px;color:#164b86}}
.smart-os-title>small{{font-size:8px;color:#8190a8}}
.smart-download-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.smart-download-app{{min-height:76px;padding:11px 13px;border:1px solid #e0e8f4;border-radius:12px;background:#fff;display:flex;align-items:center;gap:10px;text-decoration:none;color:#17233d;transition:.18s;direction:ltr}}
.smart-download-app:hover{{transform:translateY(-2px);border-color:#9dbbf0;box-shadow:0 7px 22px rgba(35,75,139,.07)}}
.smart-download-logo{{width:40px;height:40px;flex:0 0 40px;border-radius:11px;background:linear-gradient(135deg,#7153ee,#3487f4);display:grid;place-items:center;color:#fff;font-size:13px;font-weight:900}}
.smart-download-copy{{display:grid;gap:3px;min-width:0;text-align:left}}
.smart-download-copy>b{{font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.smart-download-copy>small{{font-size:7px;color:#8491a8}}
.smart-download-arrow{{margin-left:auto;color:#654ee5;font-size:12px}}
.download-panel{{border:1px solid #dfe6f4;border-radius:14px;background:#fff;padding:16px}}.panel-title{{display:flex;align-items:center;justify-content:space-between;margin-bottom:13px}}.panel-title b{{font-size:15px;color:#1553a0}}.panel-title i{{font-style:normal;font-size:18px;color:#7048ef}}.platforms{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.platform{{min-height:72px;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:10px;color:#fff;text-decoration:none;font-weight:900;gap:4px}}.platform strong{{font-size:13px;margin-bottom:7px}}
.platform-apps{{display:flex;align-items:center;justify-content:center;gap:5px;flex-wrap:wrap;width:100%}}
.platform-app{{display:inline-flex;align-items:center;justify-content:center;padding:4px 8px;border-radius:999px;background:rgba(255,255,255,.18);color:#fff;text-decoration:none;font-size:7px;font-weight:900;line-height:1.4;transition:.15s}}
.platform-app:hover{{background:rgba(255,255,255,.32);transform:translateY(-1px)}}
.platform-app.disabled{{opacity:.65;pointer-events:none}}.platform small{{font-size:8px;color:rgba(255,255,255,.88)}}.platform.android{{background:linear-gradient(135deg,#11b154,#1d8d45)}}.platform.ios{{background:linear-gradient(135deg,#2684ff,#1560d6)}}.platform.windows{{background:linear-gradient(135deg,#284fd0,#1837a3)}}.platform.macos{{background:linear-gradient(135deg,#a64ff3,#7d36e0)}}.app-more{{margin-top:9px}}.app-more summary{{cursor:pointer;text-align:center;font-size:8px;color:#6246d5;font-weight:900}}.app-more .os{{display:grid;grid-template-columns:90px 1fr;gap:8px;padding:8px 0;border-top:1px solid #eef1f7}}.app-more .os>b{{font-size:8px}}.app-more .os span{{display:flex;gap:5px;flex-wrap:wrap}}.app-more .os a{{padding:5px 7px;border-radius:6px;background:#f3f0ff;color:#6045cc;text-decoration:none;font-size:7px}}

.footer{{margin-top:16px;min-height:43px;border-radius:10px;background:#f2f5fb;display:flex;align-items:center;justify-content:space-between;padding:0 18px;color:#7585a5;font-size:8px}}.toast{{position:fixed;left:50%;bottom:22px;z-index:50;transform:translate(-50%,18px);opacity:0;pointer-events:none;padding:10px 14px;border-radius:10px;background:#15203c;color:#fff;font-size:9px;transition:.2s}}.toast.show{{opacity:1;transform:translate(-50%,0)}}.empty-state{{padding:35px;text-align:center;border:1px dashed #cbd8ec;border-radius:14px;background:#fff}}
@media(max-width:1050px){{.traffic-card{{grid-template-columns:180px 1fr}}.traffic-donut{{width:145px;height:145px}}.traffic-donut:before{{width:112px;height:112px}}.traffic-stats{{grid-template-columns:repeat(2,1fr);row-gap:12px}}.traffic-stat:nth-child(2){{border-left:0}}.protocol-grid{{gap:10px}}.details-grid{{grid-template-columns:repeat(3,1fr)}}.lower-grid{{grid-template-columns:1fr}}}}
@media(max-width:720px){{.smart-download-grid{{grid-template-columns:1fr}}.topnav{{height:auto;padding:12px 0}}.account-copy{{display:none}}.shell{{width:calc(100% - 20px);padding-top:14px}}.traffic-card{{grid-template-columns:1fr;padding:18px}}.traffic-donut{{width:135px;height:135px}}.traffic-stats{{grid-template-columns:1fr 1fr}}.traffic-stat{{padding:8px 14px}}.traffic-stat b{{font-size:19px}}.protocol-grid{{display:flex;overflow-x:auto;scrollbar-width:none}}.proto-card{{min-width:145px;flex:0 0 145px;min-height:125px}}.details-grid{{grid-template-columns:1fr 1fr}}.qr-action{{grid-template-columns:115px 1fr}}.qr-action>img{{width:108px;height:108px}}.platforms{{grid-template-columns:1fr 1fr}}.footer{{flex-direction:column;justify-content:center;gap:4px;padding:10px}}}}

/* TWINPANEL_SUBLINK_DARK_VISUAL_V2 */

html[data-theme="dark"] body{{
  background:#050608;
  color:#f5f7fa;
}}

html[data-theme="dark"] .topnav{{
  background:rgba(7,9,13,.96);
  border-bottom:1px solid rgba(255,255,255,.07);
  box-shadow:0 10px 32px rgba(0,0,0,.28);
}}

html[data-theme="dark"] .brand-mark{{
  background:linear-gradient(145deg,#7c5cff,#633ee8);
  box-shadow:0 8px 24px rgba(124,92,255,.22);
}}

html[data-theme="dark"] .avatar{{
  background:#7c5cff;
}}

html[data-theme="dark"] .online-badge{{
  background:rgba(34,197,94,.10);
  border:1px solid rgba(34,197,94,.16);
  color:#8ee8ad;
}}

html[data-theme="dark"] .theme-toggle{{
  background:#10141b;
  border-color:rgba(255,255,255,.09);
}}

html[data-theme="dark"] .theme-toggle:hover{{
  background:#171c24;
}}

/* Traffic */
html[data-theme="dark"] .traffic-card{{
  position:relative;
  overflow:hidden;
  background:
    radial-gradient(circle at 88% 5%,rgba(124,92,255,.20),transparent 28%),
    linear-gradient(145deg,#0b0e13,#0d1017);
  border:1px solid rgba(255,255,255,.075);
  box-shadow:0 18px 48px rgba(0,0,0,.30);
}}

html[data-theme="dark"] .traffic-card:after{{
  content:"";
  position:absolute;
  width:330px;
  height:330px;
  left:-150px;
  bottom:-220px;
  border-radius:50%;
  background:rgba(124,92,255,.13);
  filter:blur(55px);
  pointer-events:none;
}}

html[data-theme="dark"] .traffic-title,
html[data-theme="dark"] .traffic-stats,
html[data-theme="dark"] .progress,
html[data-theme="dark"] .traffic-donut{{
  position:relative;
  z-index:1;
}}

html[data-theme="dark"] .traffic-donut{{
  box-shadow:
    0 0 0 1px rgba(255,255,255,.06),
    0 20px 42px rgba(0,0,0,.22);
}}

html[data-theme="dark"] .traffic-donut:before{{
  background:#10131b;
}}

html[data-theme="dark"] .live{{
  background:rgba(34,197,94,.12);
  border:1px solid rgba(34,197,94,.18);
  color:#78e69e;
}}

html[data-theme="dark"] .traffic-stat{{
  border-left-color:rgba(255,255,255,.09);
}}

html[data-theme="dark"] .traffic-stat small{{
  color:#8d96a6;
}}

html[data-theme="dark"] .progress{{
  background:#171b25;
}}

/* Section title */
html[data-theme="dark"] .section-heading small{{
  color:#9278ff;
}}

html[data-theme="dark"] .section-heading h2{{
  color:#f5f7fa;
}}

html[data-theme="dark"] .section-heading p{{
  color:#8993a3;
}}

html[data-theme="dark"] .section-heading>i{{
  background:rgba(124,92,255,.11);
  color:#9278ff;
  border:1px solid rgba(124,92,255,.14);
}}

/* Protocol cards */
html[data-theme="dark"] .proto-card{{
  background:#0b0e13;
  color:#f5f7fa;
  border-color:rgba(255,255,255,.08);
  box-shadow:none;
}}

html[data-theme="dark"] .proto-card:hover{{
  background:#10141b;
  border-color:rgba(124,92,255,.34);
}}

html[data-theme="dark"] .proto-card.active{{
  background:#10141b;
  border-color:#7c5cff;
  box-shadow:
    inset 0 0 0 1px rgba(124,92,255,.10),
    0 12px 30px rgba(0,0,0,.18);
}}

html[data-theme="dark"] .proto-card small{{
  color:#8993a3;
}}

html[data-theme="dark"] .proto-card em{{
  background:#151a22 !important;
}}

/* Protocol detail */
html[data-theme="dark"] .proto-pane{{
  background:#0b0e13;
  border-color:rgba(255,255,255,.08);
  box-shadow:none;
}}

html[data-theme="dark"] .details-title{{
  border-bottom-color:rgba(255,255,255,.07);
}}

html[data-theme="dark"] .details-title strong{{
  color:#f5f7fa;
}}

html[data-theme="dark"] .details-title small{{
  color:#8993a3;
}}

html[data-theme="dark"] .node-block{{
  border-top-color:rgba(255,255,255,.06);
}}

html[data-theme="dark"] .node-title em{{
  color:#8993a3;
}}

html[data-theme="dark"] .detail-item{{
  background:#10141b;
  border-color:rgba(255,255,255,.07);
}}

html[data-theme="dark"] .detail-item small{{
  color:#8993a3;
}}

html[data-theme="dark"] .detail-item button{{
  background:rgba(124,92,255,.12);
  color:#a997ff;
}}

/* Config / QR */
html[data-theme="dark"] .delivery-action{{
  background:#10141b;
  border-color:rgba(255,255,255,.07);
}}

html[data-theme="dark"] .technical code{{
  background:#080a0e;
  color:#bbc3d0;
  border:1px solid rgba(255,255,255,.06);
}}

html[data-theme="dark"] .qr-action>img{{
  border-color:rgba(255,255,255,.09);
}}

/* Downloads */
html[data-theme="dark"] .download-panel{{
  background:#0b0e13;
  border-color:rgba(255,255,255,.08);
}}

html[data-theme="dark"] .panel-title b{{
  color:#f5f7fa;
}}

html[data-theme="dark"] .smart-os-card{{
  background:#10141b;
  border-color:rgba(255,255,255,.07);
  color:#f5f7fa;
}}

html[data-theme="dark"] .smart-os-card.active{{
  background:rgba(124,92,255,.10);
  border-color:#7c5cff;
  box-shadow:none;
}}

html[data-theme="dark"] .smart-download-app{{
  background:#10141b;
  border-color:rgba(255,255,255,.07);
  color:#f5f7fa;
}}

html[data-theme="dark"] .app-more summary{{
  color:#9278ff;
}}

html[data-theme="dark"] .app-more .os{{
  border-top-color:rgba(255,255,255,.06);
}}

html[data-theme="dark"] .app-more .os a{{
  background:rgba(124,92,255,.10);
  color:#a997ff;
}}

/* Footer */
html[data-theme="dark"] .footer{{
  background:#080a0e;
  border:1px solid rgba(255,255,255,.06);
  color:#8993a3;
}}

html[data-theme="dark"] .empty-state{{
  background:#0b0e13;
  border-color:rgba(255,255,255,.10);
}}


/* TWINPANEL_SUBLINK_POLISH_V3 */

html[data-theme="dark"] .topnav{{
  height:74px;
}}

html[data-theme="dark"] .traffic-card{{
  grid-template-columns:190px 1fr;
  gap:22px;
  padding:20px 26px;
  min-height:188px;
}}

html[data-theme="dark"] .traffic-donut{{
  width:150px;
  height:150px;
}}

html[data-theme="dark"] .traffic-donut:before{{
  width:116px;
  height:116px;
}}

html[data-theme="dark"] .traffic-donut b{{
  font-size:32px;
}}

html[data-theme="dark"] .traffic-title{{
  margin-bottom:15px;
}}

html[data-theme="dark"] .traffic-title h2{{
  font-size:19px;
}}

html[data-theme="dark"] .traffic-stat{{
  min-height:68px;
  padding:2px 22px;
}}

html[data-theme="dark"] .traffic-stat small{{
  font-size:10px;
}}

html[data-theme="dark"] .traffic-stat b{{
  font-size:24px;
  margin-top:6px;
}}

html[data-theme="dark"] .traffic-stat.time b{{
  font-size:17px;
}}

html[data-theme="dark"] .progress{{
  height:8px;
  margin-top:14px;
}}

html[data-theme="dark"] .section-heading{{
  margin-top:18px;
  margin-bottom:11px;
}}

html[data-theme="dark"] .section-heading h2{{
  font-size:19px;
}}

html[data-theme="dark"] .section-heading small{{
  font-size:9px;
}}

html[data-theme="dark"] .section-heading p{{
  font-size:9px;
  line-height:1.8;
}}

html[data-theme="dark"] .protocol-grid{{
  gap:18px;
}}

html[data-theme="dark"] .proto-card{{
  min-height:132px;
  gap:6px;
  border-radius:15px;
}}

html[data-theme="dark"] .proto-logo{{
  width:51px;
  height:51px;
}}

html[data-theme="dark"] .proto-card b{{
  font-size:12px;
}}

html[data-theme="dark"] .proto-card small{{
  font-size:8px;
}}

html[data-theme="dark"] .proto-card em{{
  padding:4px 12px;
  font-size:8px;
}}

html[data-theme="dark"] .proto-pane{{
  margin-top:12px;
}}

html[data-theme="dark"] .details-title{{
  padding:14px 18px;
}}

html[data-theme="dark"] .details-title strong{{
  font-size:15px;
}}

html[data-theme="dark"] .details-title small{{
  font-size:8px;
}}

html[data-theme="dark"] .detail-item{{
  min-height:108px;
}}

html[data-theme="dark"] .detail-item small{{
  font-size:8px;
}}

html[data-theme="dark"] .detail-item b{{
  font-size:10px;
}}

@media(max-width:720px){{
  html[data-theme="dark"] .topnav{{
    height:auto;
  }}

  html[data-theme="dark"] .traffic-card{{
    grid-template-columns:1fr;
    min-height:0;
    padding:18px;
  }}
}}


/* TWINPANEL_SUBLINK_READABLE_V4 */

/* Protocols */
html[data-theme="dark"] .proto-card b{{
  font-size:13px;
}}

html[data-theme="dark"] .proto-card small{{
  font-size:9px;
  line-height:1.5;
}}

html[data-theme="dark"] .proto-card em{{
  font-size:9px;
  min-width:36px;
  text-align:center;
}}

/* Protocol detail header */
html[data-theme="dark"] .details-title strong{{
  font-size:16px;
}}

html[data-theme="dark"] .details-title small{{
  font-size:9px;
}}

html[data-theme="dark"] .node-title b{{
  font-size:11px;
}}

html[data-theme="dark"] .node-title em{{
  font-size:9px;
}}

/* Credential cards */
html[data-theme="dark"] .detail-item{{
  min-height:116px;
  padding:15px 12px;
}}

html[data-theme="dark"] .detail-icon{{
  width:34px;
  height:34px;
  border-radius:10px;
  font-size:14px;
}}

html[data-theme="dark"] .detail-item small{{
  font-size:9px;
}}

html[data-theme="dark"] .detail-item b{{
  font-size:11px;
  line-height:1.6;
}}

html[data-theme="dark"] .detail-item button{{
  min-height:27px;
  padding:5px 15px;
  font-size:9px;
}}

/* Download section */
html[data-theme="dark"] .download-panel{{
  padding:20px;
}}

html[data-theme="dark"] .panel-title{{
  margin-bottom:17px;
}}

html[data-theme="dark"] .panel-title b{{
  font-size:17px;
}}

html[data-theme="dark"] .panel-title i{{
  font-size:20px;
}}

html[data-theme="dark"] .smart-download-grid{{
  gap:11px;
}}

html[data-theme="dark"] .smart-download-app{{
  min-height:88px;
  padding:13px 15px;
  gap:12px;
  border-radius:14px;
}}

html[data-theme="dark"] .smart-download-logo{{
  width:45px;
  height:45px;
  flex:0 0 45px;
  border-radius:13px;
  font-size:14px;
}}

html[data-theme="dark"] .smart-download-app b{{
  font-size:10px;
  line-height:1.5;
}}

html[data-theme="dark"] .smart-download-app small{{
  font-size:8px;
  line-height:1.6;
  color:#8993a3;
}}

html[data-theme="dark"] .app-more summary{{
  font-size:9px;
  padding:6px 0;
}}

/* Footer */
html[data-theme="dark"] .footer{{
  min-height:48px;
  font-size:9px;
}}

/* Slightly better general muted text */
html[data-theme="dark"] .technical,
html[data-theme="dark"] .delivery-action small{{
  font-size:9px;
  line-height:1.7;
}}

@media(max-width:720px){{
  html[data-theme="dark"] .smart-download-app{{
    min-height:78px;
  }}

  html[data-theme="dark"] .detail-item{{
    min-height:105px;
  }}
}}


/* TWINPANEL_SUBLINK_HEADER_TRAFFIC_V6 */

/* Header */
html[data-theme="dark"] .topnav{{
  height:70px;
  background:rgba(5,6,8,.97);
  border-bottom:1px solid rgba(255,255,255,.07);
  box-shadow:0 8px 28px rgba(0,0,0,.28);
}}

html[data-theme="dark"] .brand-mark{{
  width:40px;
  height:40px;
  border-radius:12px;
  background:linear-gradient(145deg,#7c5cff,#6745e8);
  box-shadow:0 8px 22px rgba(124,92,255,.20);
}}

html[data-theme="dark"] .brand b{{
  font-size:21px;
  letter-spacing:-.35px;
}}

html[data-theme="dark"] .account-head{{
  gap:14px;
}}

html[data-theme="dark"] .avatar{{
  width:40px;
  height:40px;
  background:#7c5cff;
}}

html[data-theme="dark"] .account-copy{{
  column-gap:18px;
}}

html[data-theme="dark"] .account-copy b{{
  font-size:12px;
}}

html[data-theme="dark"] .account-copy small{{
  font-size:8px;
  color:#8993a3;
}}

html[data-theme="dark"] .online-badge{{
  padding:6px 10px;
  background:rgba(34,197,94,.10);
  border:1px solid rgba(34,197,94,.16);
  color:#78e69e;
}}

html[data-theme="dark"] .theme-toggle{{
  width:36px;
  height:36px;
  border-radius:11px;
}}

/* Traffic card */
html[data-theme="dark"] .traffic-card{{
  grid-template-columns:175px 1fr;
  gap:20px;
  min-height:170px;
  padding:18px 24px;
  border-radius:20px;
  background:
    radial-gradient(circle at 92% 3%,rgba(124,92,255,.16),transparent 27%),
    linear-gradient(145deg,#0b0e13,#0c0f16);
  border:1px solid rgba(255,255,255,.075);
  box-shadow:0 16px 42px rgba(0,0,0,.26);
}}

html[data-theme="dark"] .traffic-donut{{
  width:138px;
  height:138px;
}}

html[data-theme="dark"] .traffic-donut:before{{
  width:108px;
  height:108px;
  background:#0d1017;
}}

html[data-theme="dark"] .traffic-donut b{{
  font-size:30px;
}}

html[data-theme="dark"] .traffic-donut small{{
  font-size:8px;
  color:#8993a3;
}}

html[data-theme="dark"] .traffic-title{{
  margin-bottom:12px;
}}

html[data-theme="dark"] .traffic-title h2{{
  font-size:18px;
  letter-spacing:-.2px;
}}

html[data-theme="dark"] .live{{
  padding:5px 9px;
  font-size:8px;
}}

html[data-theme="dark"] .traffic-stat{{
  min-height:62px;
  padding:2px 20px;
  border-left-color:rgba(255,255,255,.075);
}}

html[data-theme="dark"] .traffic-stat small{{
  font-size:9px;
  color:#8993a3;
}}

html[data-theme="dark"] .traffic-stat b{{
  font-size:23px;
  margin-top:5px;
}}

html[data-theme="dark"] .traffic-stat.time b{{
  font-size:16px;
}}

html[data-theme="dark"] .progress{{
  height:7px;
  margin-top:11px;
  background:#161a22;
}}

html[data-theme="dark"] .progress i{{
  background:linear-gradient(90deg,#7c5cff,#37b6e9);
}}

@media(max-width:720px){{
  html[data-theme="dark"] .topnav{{
    height:auto;
  }}

  html[data-theme="dark"] .traffic-card{{
    grid-template-columns:1fr;
    min-height:0;
    padding:17px;
  }}

  html[data-theme="dark"] .traffic-donut{{
    width:125px;
    height:125px;
  }}

  html[data-theme="dark"] .traffic-donut:before{{
    width:97px;
    height:97px;
  }}

  html[data-theme="dark"] .traffic-stat{{
    padding:7px 11px;
  }}
}}



/* TWINPANEL_SUBLINK_LIGHT_SIZE_MATCH_DARK_V7 */

/*
   Light mode uses exactly the same geometry as Dark.
   Only colors remain theme-specific.
*/

html:not([data-theme="dark"]) .topnav{{
  height:74px;
}}

html:not([data-theme="dark"]) .traffic-card{{
  grid-template-columns:240px 1fr;
  gap:22px;
  padding:20px 26px;
  min-height:188px;
}}

html:not([data-theme="dark"]) .traffic-donut{{
  width:150px;
  height:150px;
}}

html:not([data-theme="dark"]) .traffic-donut:before{{
  width:116px;
  height:116px;
}}

html:not([data-theme="dark"]) .traffic-donut b{{
  font-size:32px;
}}

html:not([data-theme="dark"]) .traffic-title h2{{
  font-size:19px;
}}

html:not([data-theme="dark"]) .traffic-stat{{
  min-height:68px;
  padding:2px 22px;
}}

html:not([data-theme="dark"]) .traffic-stat small{{
  font-size:10px;
}}

html:not([data-theme="dark"]) .traffic-stat b{{
  font-size:24px;
}}

html:not([data-theme="dark"]) .traffic-stat.time b{{
  font-size:17px;
}}

html:not([data-theme="dark"]) .progress{{
  height:8px;
}}

html:not([data-theme="dark"]) .section-heading h2{{
  font-size:19px;
}}

html:not([data-theme="dark"]) .section-heading small{{
  font-size:9px;
}}

html:not([data-theme="dark"]) .section-heading p{{
  font-size:9px;
  line-height:1.8;
}}

html:not([data-theme="dark"]) .protocol-grid{{
  gap:18px;
}}

html:not([data-theme="dark"]) .proto-card{{
  min-height:132px;
  gap:6px;
}}

html:not([data-theme="dark"]) .proto-logo{{
  width:51px;
  height:51px;
}}

html:not([data-theme="dark"]) .proto-card b{{
  font-size:12px;
}}

html:not([data-theme="dark"]) .proto-card small{{
  font-size:8px;
}}

html:not([data-theme="dark"]) .proto-card em{{
  padding:4px 12px;
  font-size:8px;
}}

html:not([data-theme="dark"]) .details-title{{
  padding:14px 18px;
}}

html:not([data-theme="dark"]) .details-title strong{{
  font-size:15px;
}}

html:not([data-theme="dark"]) .details-title small{{
  font-size:8px;
}}

html:not([data-theme="dark"]) .detail-item{{
  min-height:108px;
}}

html:not([data-theme="dark"]) .detail-item small{{
  font-size:8px;
}}

html:not([data-theme="dark"]) .detail-item b{{
  font-size:10px;
}}


/* Mobile keeps the existing responsive layout */

@media(max-width:720px){{

  html:not([data-theme="dark"]) .topnav{{
    height:auto;
  }}

  html:not([data-theme="dark"]) .traffic-card{{
    grid-template-columns:1fr;
    min-height:0;
    padding:18px;
  }}

}}




/* TWINPANEL_SUBLINK_LIGHT_PRO_V8 */

/* Page */
html:not([data-theme="dark"]) body{{
  background:
    linear-gradient(180deg,#f7f8fb 0%,#eef1f6 100%) !important;
  color:#141823 !important;
}}

html:not([data-theme="dark"]) .shell{{
  color:#141823 !important;
}}


/* Top navigation */
html:not([data-theme="dark"]) .topnav{{
  background:rgba(255,255,255,.94) !important;
  color:#161b26 !important;
  border-bottom:1px solid #e5e8ef !important;
  box-shadow:0 8px 30px rgba(18,27,44,.055) !important;
  backdrop-filter:blur(16px);
}}

html:not([data-theme="dark"]) .brand b{{
  color:#161b26 !important;
}}

html:not([data-theme="dark"]) .account-copy b{{
  color:#1b2230 !important;
}}

html:not([data-theme="dark"]) .account-copy small{{
  color:#7d8798 !important;
}}

html:not([data-theme="dark"]) .online-badge{{
  background:#eaf8f1 !important;
  color:#168451 !important;
}}

html:not([data-theme="dark"]) .avatar{{
  color:#fff !important;
}}

html:not([data-theme="dark"]) .theme-toggle{{
  background:#f4f5f8 !important;
  color:#5f46d8 !important;
  border-color:#dfe3eb !important;
  box-shadow:none !important;
}}

html:not([data-theme="dark"]) .theme-toggle:hover{{
  background:#ebeef4 !important;
}}


/* Traffic hero */
html:not([data-theme="dark"]) .traffic-card{{
  background:
    linear-gradient(
      135deg,
      #ffffff 0%,
      #f5f3ff 58%,
      #eef3ff 100%
    ) !important;

  color:#161b26 !important;

  border:1px solid #e1e4ee !important;

  box-shadow:
    0 14px 38px rgba(31,42,68,.075) !important;
}}

html:not([data-theme="dark"]) .traffic-title h2{{
  color:#202638 !important;
}}

html:not([data-theme="dark"]) .live{{
  background:#e6f7ef !important;
  color:#168451 !important;
}}

html:not([data-theme="dark"]) .traffic-stat{{
  border-left-color:#dde2eb !important;
}}

html:not([data-theme="dark"]) .traffic-stat small{{
  color:#7b8495 !important;
}}

html:not([data-theme="dark"]) .traffic-stat b{{
  color:#222938 !important;
}}

html:not([data-theme="dark"]) .traffic-donut{{
  background:
    conic-gradient(
      #ff9b38 0 7%,
      #7257ee 7% {pct}%,
      #e4e6ed {pct}% 100%
    ) !important;
}}

html:not([data-theme="dark"]) .traffic-donut:before{{
  background:#ffffff !important;
}}

html:not([data-theme="dark"]) .traffic-donut b{{
  color:#242a3a !important;
}}

html:not([data-theme="dark"]) .traffic-donut small{{
  color:#7f8898 !important;
}}

html:not([data-theme="dark"]) .progress{{
  background:#e5e8ef !important;
}}


/* Section headings */
html:not([data-theme="dark"]) .section-heading small{{
  color:#7257e8 !important;
}}

html:not([data-theme="dark"]) .section-heading h2{{
  color:#1d2533 !important;
}}

html:not([data-theme="dark"]) .section-heading p{{
  color:#818b9c !important;
}}

html:not([data-theme="dark"]) .section-heading>i{{
  background:#efedff !important;
  color:#7054e8 !important;
}}


/* Protocol cards */
html:not([data-theme="dark"]) .proto-card{{
  background:#ffffff !important;
  color:#1a2130 !important;

  border-color:#e1e5ed !important;

  box-shadow:
    0 7px 20px rgba(35,45,65,.045) !important;
}}

html:not([data-theme="dark"]) .proto-card:hover{{
  box-shadow:
    0 12px 28px rgba(43,54,80,.075) !important;
}}

html:not([data-theme="dark"]) .proto-card.active{{
  border-color:#7559ed !important;

  box-shadow:
    0 0 0 1px rgba(117,89,237,.10),
    0 10px 26px rgba(89,66,190,.08) !important;
}}

html:not([data-theme="dark"]) .proto-card small{{
  color:#818a99 !important;
}}


/* Protocol details */
html:not([data-theme="dark"]) .proto-pane{{
  background:#ffffff !important;
  border-color:#dfe4ec !important;

  box-shadow:
    0 10px 28px rgba(28,40,65,.05) !important;
}}

html:not([data-theme="dark"]) .details-title{{
  border-bottom-color:#e6e9ef !important;
}}

html:not([data-theme="dark"]) .details-title strong{{
  color:#202838 !important;
}}

html:not([data-theme="dark"]) .details-title small,
html:not([data-theme="dark"]) .node-title em{{
  color:#818b9b !important;
}}

html:not([data-theme="dark"]) .node-block{{
  border-color:#e8ebf0 !important;
}}

html:not([data-theme="dark"]) .detail-item{{
  background:#f8f9fb !important;
  border-color:#e3e7ee !important;
}}

html:not([data-theme="dark"]) .detail-item small{{
  color:#7b8597 !important;
}}

html:not([data-theme="dark"]) .detail-item b{{
  color:#1c2331 !important;
}}

html:not([data-theme="dark"]) .detail-item button{{
  background:#eceafe !important;
  color:#654bd7 !important;
}}


/* Downloads */
html:not([data-theme="dark"]) .download-panel,
html:not([data-theme="dark"]) .delivery-action{{
  background:#ffffff !important;
  border-color:#e0e4eb !important;

  box-shadow:
    0 8px 24px rgba(28,39,61,.045) !important;
}}

html:not([data-theme="dark"]) .panel-title b{{
  color:#202838 !important;
}}

html:not([data-theme="dark"]) .smart-os-card,
html:not([data-theme="dark"]) .smart-download-app{{
  background:#ffffff !important;
  border-color:#e1e5ec !important;
  color:#1b2230 !important;
}}

html:not([data-theme="dark"]) .smart-os-card.active{{
  background:#f5f3ff !important;
  border-color:#7760e8 !important;
}}

html:not([data-theme="dark"]) .smart-download-app:hover{{
  background:#f8f7ff !important;
  border-color:#cfc7f7 !important;
}}


/* Footer */
html:not([data-theme="dark"]) .footer{{
  background:#e9edf3 !important;
  color:#747f90 !important;
  border:1px solid #dfe3e9 !important;
}}


/* TWINPANEL_SUBLINK_SERVER_SELECTOR_V4B */
.traffic-stats{{grid-template-columns:repeat(6,minmax(0,1fr))!important}}
.traffic-stat{{min-width:0;min-height:66px!important;padding:4px 10px!important}}
.traffic-stat b{{font-size:19px!important}}
.traffic-stat.date b{{font-size:14px!important;direction:ltr;text-align:right;white-space:nowrap}}

.server-switcher{{display:flex;gap:7px;overflow-x:auto;padding:10px 16px 8px}}
.server-chip{{flex:0 0 auto;min-width:76px;height:34px;padding:0 11px;border:1px solid rgba(130,110,200,.28);border-radius:9px;background:rgba(120,95,200,.07);color:inherit;cursor:pointer;font-size:11px;font-weight:800}}
.server-chip i{{display:inline-block;width:6px;height:6px;border-radius:50%;background:#20c982;margin-left:6px}}
.server-chip.active{{border-color:#7657ef;background:rgba(118,87,239,.16);color:#8b74ff}}

.server-panel{{display:none!important}}
.server-panel.active{{display:block!important;margin:3px 16px 14px!important;padding:10px!important;min-height:0!important}}
.server-panel .node-title{{margin:0 0 8px!important;min-height:22px!important}}
.server-panel .details-grid{{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))!important;gap:8px!important}}
.server-panel .detail-item{{min-height:56px!important;padding:8px!important;border-radius:10px!important}}
.server-panel .detail-item b{{font-size:12px!important}}
.server-panel .detail-item small{{font-size:9px!important}}

@media(max-width:1050px){{.traffic-stats{{grid-template-columns:repeat(3,minmax(0,1fr))!important}}}}
@media(max-width:720px){{.traffic-stats{{grid-template-columns:repeat(2,minmax(0,1fr))!important}}.server-switcher{{padding:8px 10px}}.server-panel.active{{margin:3px 10px 12px!important}}}}


/* TWINPANEL_SERVER_SELECTOR_POLISH_V1 */
.server-panel .node-title{{display:none!important}}
.server-switcher{{padding-bottom:6px!important}}
.server-panel.active{{
  margin:0 16px 12px!important;
  padding:6px 10px 10px!important;
}}
.server-panel .details-grid{{
  gap:7px!important;
}}
.server-panel .detail-item{{
  min-height:50px!important;
  padding:6px 8px!important;
}}
.server-panel .detail-icon{{
  width:26px!important;
  height:26px!important;
  flex:0 0 26px!important;
}}
.server-panel .detail-item button{{
  padding:4px 7px!important;
  font-size:9px!important;
}}
@media(max-width:720px){{
  .server-panel.active{{
    margin:0 10px 10px!important;
  }}
}}

</style>

<!-- TWINPANEL_PUBLIC_SUB_EXTERNAL_CSS_V1 -->
<link
  rel="stylesheet"
  href="/connect-assets/unified-v1.css?v=1"
>
</head>
<body>
<header class="topnav"><div class="topnav-inner">
<div class="brand">
<button class="theme-toggle" id="themeToggle" type="button" aria-label="تغییر حالت نمایش">☾</button>
<span class="brand-mark">{_h(brand_mark)}</span><b>{_h(brand_name)}</b>
</div>
<div class="account-head"><span class="online-badge"><i></i> اشتراک فعال</span>
<div class="account-copy"><b>{_h(title)}</b><b>{_h(user_name)}</b><small>تاریخ انقضا: {_h(expires)}</small><small>حساب کاربری</small></div>
<span class="avatar">{_h((user_name[:1] or "M").upper())}</span></div>
</div></header>

<main class="shell">
<section class="traffic-card">
<div class="traffic-donut" id="trafficDonut"><span><b id="donutPercent">{pct:.0f}%</b><small>مصرف شده</small></span></div>
<div class="traffic-main"><div class="traffic-title"><span class="live">LIVE</span><h2>مصرف ترافیک</h2></div>
<div class="traffic-stats">
<div class="traffic-stat"><small>مصرف‌شده</small><b id="used">{_h(used_label)}</b></div>
<div class="traffic-stat"><small>باقی‌مانده</small><b id="remaining">{_h(remaining_label)}</b></div>
<div class="traffic-stat"><small>حجم کل</small><b id="total">{_h(total_label)}</b></div>
<div class="traffic-stat date"><small>تاریخ شروع</small><b>{_h(starts)}</b></div>
<div class="traffic-stat date"><small>تاریخ انقضا</small><b>{_h(expires)}</b></div>
<div class="traffic-stat time"><small>آخرین بروزرسانی</small><b id="lastUpdate">همین حالا</b></div>
</div><div class="progress"><i id="usageBar"></i></div></div>
</section>

{body}

<div class="lower-grid">
<section class="download-panel"><div class="panel-title"><i>☁</i><b>دانلود برنامه‌ها</b></div>
{smart_apps}</section>


</div>

<footer class="footer"><span>◈ اتصال شما با رمزنگاری قوی محافظت می‌شود</span><b>{_h(brand_name)} ©</b><span>نسخه 5.0</span></footer>
</main>
<div class="toast" id="toast">کپی شد ✓</div>

<script>
const SUB_TOKEN={json.dumps(token)};
const nf=new Intl.NumberFormat('fa-IR',{{maximumFractionDigits:1}});

// TWINPANEL_CONNECT_DARK_MODE_V1
const CONNECT_THEME_KEY="twinpanel_connect_theme";
const themeButton=document.getElementById("themeToggle");

function applyConnectTheme(theme){{
    const value=theme==="dark"?"dark":"light";

    document.documentElement.dataset.theme=value;

    if(themeButton){{
        themeButton.textContent=
            value==="dark"
            ? "☀"
            : "☾";

        themeButton.title=
            value==="dark"
            ? "Light mode"
            : "Dark mode";
    }}
}}

let savedConnectTheme=null;

try{{
    savedConnectTheme=
        localStorage.getItem(
            CONNECT_THEME_KEY
        );
}}catch(_e){{}}

const prefersDark=
    window.matchMedia
    &&
    window.matchMedia(
        "(prefers-color-scheme: dark)"
    ).matches;

applyConnectTheme(
    savedConnectTheme
    ||
    (prefersDark ? "dark" : "light")
);

if(themeButton){{
    themeButton.addEventListener(
        "click",
        function(){{
            const next=
                document.documentElement.dataset.theme
                === "dark"
                ? "light"
                : "dark";

            applyConnectTheme(next);

            try{{
                localStorage.setItem(
                    CONNECT_THEME_KEY,
                    next
                );
            }}catch(_e){{}}
        }}
    );
}}
// TWINPANEL_SERVER_SELECTOR_JS_V4B
document.addEventListener('click',function(e){{
 const btn=e.target.closest('.server-chip');if(!btn)return;
 const pane=btn.closest('.proto-pane');if(!pane)return;
 const n=btn.dataset.serverIndex;
 pane.querySelectorAll('.server-chip').forEach(x=>x.classList.toggle('active',x===btn));
 pane.querySelectorAll('.server-panel').forEach(x=>x.classList.toggle('active',x.dataset.serverIndex===n));
}});
const tabs=[...document.querySelectorAll('.proto-card')];
const panes=[...document.querySelectorAll('.proto-pane')];
tabs.forEach(btn=>btn.addEventListener('click',()=>{{tabs.forEach(x=>x.classList.remove('active'));panes.forEach(x=>x.classList.remove('active'));btn.classList.add('active');const pane=document.querySelector(`[data-pane="${{btn.dataset.tab}}"]`);if(pane)pane.classList.add('active');}}));
function toast(){{const el=document.getElementById('toast');el.classList.add('show');setTimeout(()=>el.classList.remove('show'),1200);}}
document.addEventListener('click',async e=>{{const btn=e.target.closest('[data-copy]');if(!btn)return;try{{await navigator.clipboard.writeText(btn.dataset.copy||'');toast();}}catch(_e){{}}}});
function gb(v){{return `${{nf.format(Number(v||0))}} GB`;}}
function ago(iso){{if(!iso)return 'بدون مصرف';const sec=Math.max(0,Math.floor((Date.now()-new Date(iso).getTime())/1000));if(sec<15)return 'همین حالا';if(sec<60)return `${{nf.format(sec)}} ثانیه پیش`;if(sec<3600)return `${{nf.format(Math.floor(sec/60))}} دقیقه پیش`;return new Date(iso).toLocaleTimeString('fa-IR',{{hour:'2-digit',minute:'2-digit'}});}}
async function refreshUsage(){{try{{const r=await fetch(`/v1/connect/${{SUB_TOKEN}}/usage`,{{cache:'no-store'}});if(!r.ok)return;const u=await r.json();const pct=u.unlimited?0:Number(u.percent||0);document.getElementById('used').textContent=gb(u.used_gb);document.getElementById('remaining').textContent=u.unlimited?'∞':gb(u.remaining_gb);document.getElementById('total').textContent=u.unlimited?'نامحدود':gb(u.total_gb);document.getElementById('lastUpdate').textContent=ago(u.last_usage_event_at||u.refreshed_at);document.getElementById('usageBar').style.width=`${{pct}}%`;document.getElementById('donutPercent').textContent=u.unlimited?'∞':`${{nf.format(pct)}}%`;document.getElementById('trafficDonut').style.background=`conic-gradient(#ff9b38 0 7%,#0fc8e5 7% ${{pct}}%,rgba(255,255,255,.16) ${{pct}}% 100%)`;}}catch(_e){{}}}}
refreshUsage();setInterval(refreshUsage,8000);

// TWINPANEL_SMART_OS_DETECT_V2
(function(){{
    const buttons = Array.from(
        document.querySelectorAll(
            "[data-app-os]"
        )
    );

    const panels = Array.from(
        document.querySelectorAll(
            "[data-app-panel]"
        )
    );

    if(!buttons.length){{
        return;
    }}

    function available(os){{
        return buttons.some(
            function(btn){{
                return btn.dataset.appOs === os;
            }}
        );
    }}

    function detectOS(){{
        const ua = String(
            navigator.userAgent || ""
        ).toLowerCase();

        const platform = String(
            navigator.platform || ""
        ).toLowerCase();

        if(
            /iphone|ipad|ipod/.test(ua)
            ||
            (
                platform === "macintel"
                &&
                navigator.maxTouchPoints > 1
            )
        ){{
            return "ios";
        }}

        if(/android/.test(ua)){{
            return "android";
        }}

        if(
            /windows/.test(ua)
            ||
            /win/.test(platform)
        ){{
            return "windows";
        }}

        if(
            /macintosh|mac os/.test(ua)
            ||
            /mac/.test(platform)
        ){{
            return "macos";
        }}

        if(/linux/.test(ua)){{
            return "linux";
        }}

        return "";
    }}

    function selectOS(os){{
        if(!available(os)){{
            os = buttons[0].dataset.appOs;
        }}

        buttons.forEach(
            function(btn){{
                btn.classList.toggle(
                    "active",
                    btn.dataset.appOs === os
                );
            }}
        );

        panels.forEach(
            function(panel){{
                panel.classList.toggle(
                    "active",
                    panel.dataset.appPanel === os
                );
            }}
        );
    }}

    buttons.forEach(
        function(btn){{
            btn.addEventListener(
                "click",
                function(){{
                    selectOS(
                        btn.dataset.appOs
                    );
                }}
            );
        }}
    );

    selectOS(
        detectOS()
        || buttons[0].dataset.appOs
    );
}})();
</script>
</body></html>'''
    return HTMLResponse(page)


def _find_item(payload: dict[str, Any], protocol: str, node_id: int) -> dict[str, Any]:
    for cred in payload.get("credentials", []):
        if cred.get("protocol") != protocol:
            continue
        for item in cred.get("items", []):
            if int(item.get("node_id", -1)) == node_id:
                return item
    raise HTTPException(status_code=404, detail="فایل کانفیگ پیدا نشد")


@public_router.get("/{token}/file/{protocol}/{node_id}")
def public_config_file(token: str, protocol: str, node_id: int, db: Session = Depends(get_db)):
    if protocol not in {"openvpn", "wireguard"}:
        raise HTTPException(status_code=404, detail="نوع فایل پشتیبانی نمی‌شود")
    sub = _subscription_from_share_token(token, db)
    payload = _public_payload(db, sub)
    item = _find_item(payload, protocol, node_id)
    config = item.get("config")
    if not config:
        raise HTTPException(status_code=404, detail="فایل کانفیگ موجود نیست")
    # Always expose account + country as the downloaded filename,
    # including credentials provisioned before this change.
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    user = db.get(User, sub.user_id)

    extension = (
        "ovpn"
        if protocol == "openvpn"
        else "conf"
    )

    if node and user:
        filename = _account_country_filename(
            sub,
            user,
            node,
            extension,
        )
    else:
        username = _download_filename_part(
            sub.account_username,
            f"user{sub.id}",
        )
        filename = f"{username}-Server.{extension}"
    media = "application/x-openvpn-profile" if protocol == "openvpn" else "text/plain; charset=utf-8"
    return Response(config, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# TWINPANEL_SUB_MANUAL_LIMITS_V16
@router.patch("/{subscription_id}/manual-limits")
def set_manual_limits(
    subscription_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    try:
        traffic_gb = float(payload.get("traffic_gb", 0))
        duration_days = int(payload.get("duration_days", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid traffic or duration")

    if traffic_gb <= 0 or duration_days <= 0:
        raise HTTPException(
            status_code=422,
            detail="traffic_gb and duration_days must be greater than zero",
        )

    now = datetime.utcnow()
    sub.traffic_limit_bytes = int(
        traffic_gb
        * 1024
        * 1024
        * 1024
    )

    # TWINPANEL_FIRST_USE_MANUAL_LIMITS_V2
    if (
        sub.starts_at is None
        and sub.expires_at is None
    ):
        # Waiting subscription:
        # change purchased duration only.
        sub.activation_duration_days = (
            int(duration_days)
        )

    else:
        # Already-started subscription keeps
        # the legacy manual-limit semantics.
        if not sub.starts_at:
            sub.starts_at = now

        sub.expires_at = (
            now
            + timedelta(
                days=duration_days
            )
        )

    db.commit()
    db.refresh(sub)
    return {
        "ok": True,
        "subscription_id": sub.id,
        "traffic_limit_bytes": sub.traffic_limit_bytes,
        "traffic_used_bytes": sub.traffic_used_bytes,
        "starts_at": sub.starts_at,
        "expires_at": sub.expires_at,
    }

# TWINPANEL_SUB_COMPLETE_V17
@router.patch("/{subscription_id}/extend")
def extend_subscription_v17(subscription_id:int,payload:dict=Body(...),db:Session=Depends(get_db)):
    sub=db.get(Subscription,subscription_id)
    if not sub: raise HTTPException(status_code=404,detail="اشتراک پیدا نشد")
    add_traffic_gb=float(payload.get("add_traffic_gb",0) or 0)
    add_days=int(payload.get("add_days",0) or 0)
    if add_traffic_gb<=0 and add_days<=0: raise HTTPException(status_code=422,detail="مقداری برای افزایش وارد نشده")
    if add_traffic_gb>0:
        sub.traffic_limit_bytes=int(sub.traffic_limit_bytes or 0)+int(add_traffic_gb*1024**3)
    if add_days>0:
        # TWINPANEL_FIRST_USE_EXTEND_V1
        if (
            sub.starts_at is None
            and sub.expires_at is None
        ):
            current_days = int(
                sub.activation_duration_days
                or 0
            )

            if current_days <= 0:
                from ..models import Plan as _FirstUsePlan

                _plan = db.get(
                    _FirstUsePlan,
                    sub.plan_id,
                )

                current_days = int(
                    _plan.duration_days
                    if _plan
                    else 0
                )

            if current_days <= 0:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "مدت اشتراک برای فعال‌سازی "
                        "اولیه مشخص نیست"
                    ),
                )

            sub.activation_duration_days = (
                current_days
                + add_days
            )

        else:
            now=datetime.utcnow()
            base=(
                sub.expires_at
                if (
                    sub.expires_at
                    and sub.expires_at>now
                )
                else now
            )
            sub.expires_at=(
                base
                + timedelta(days=add_days)
            )
    db.commit();db.refresh(sub)
    return {"ok":True,"traffic_limit_bytes":int(sub.traffic_limit_bytes or 0),"traffic_used_bytes":int(sub.traffic_used_bytes or 0),"expires_at":sub.expires_at.isoformat() if sub.expires_at else None}

@router.patch("/{subscription_id}/admin-edit")
async def admin_edit_subscription_v18(
    subscription_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    # TWINPANEL_SUBSCRIPTION_RECONCILE_V18
    from ..models import Plan

    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    user = db.get(
        User,
        sub.user_id,
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    # ------------------------------------------------------
    # Current state
    # ------------------------------------------------------

    old_node_ids = {
        int(row.node_id)
        for row in (
            db.query(SubscriptionNode)
            .filter(
                SubscriptionNode.subscription_id
                == sub.id
            )
            .all()
        )
    }

    old_protocols = {
        str(row.protocol).lower()
        for row in (
            db.query(SubscriptionProtocol)
            .filter(
                SubscriptionProtocol.subscription_id
                == sub.id
            )
            .all()
        )
    }

    # ------------------------------------------------------
    # Plan + traffic
    # ------------------------------------------------------

    plan_id = int(
        payload.get("plan_id")
        or sub.plan_id
    )

    plan = db.get(
        Plan,
        plan_id,
    )

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="پلن پیدا نشد",
        )

    traffic_gb = float(
        payload.get(
            "traffic_gb",
            0,
        )
        or 0
    )

    if traffic_gb <= 0:
        raise HTTPException(
            status_code=422,
            detail="حجم نامعتبر است",
        )

    new_limit = int(
        traffic_gb
        * 1024 ** 3
    )

    if new_limit < int(
        sub.traffic_used_bytes
        or 0
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "حجم کل کمتر از "
                "مصرف فعلی است"
            ),
        )

    # ------------------------------------------------------
    # TWINPANEL_GLOBAL_NODE_ASSIGNMENT_V1
    # ------------------------------------------------------
    #
    # Node membership is global. The subscription edit API may
    # still receive node_ids from an older frontend, but they do
    # not restrict access anymore.

    nodes = (
        db.query(Node).filter(Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )

    node_ids = [
        int(node.id)
        for node in nodes
    ]


    # ------------------------------------------------------
    # Protocol validation
    # ------------------------------------------------------

    protocols = list(
        dict.fromkeys(
            str(x)
            .strip()
            .lower()
            for x in payload.get(
                "protocols",
                [],
            )
            if str(x).strip()
        )
    )

    field_map = {
        "cisco": "enable_cisco",
        "openvpn": "enable_openvpn",
        "wireguard": "enable_wireguard",
        "l2tp": "enable_l2tp",
        "v2ray": "enable_v2ray",
    }

    bad = [
        key
        for key in protocols
        if key not in field_map
    ]

    if bad:
        raise HTTPException(
            status_code=422,
            detail=(
                "پروتکل نامعتبر: "
                + ", ".join(bad)
            ),
        )

    if not protocols:
        raise HTTPException(
            status_code=422,
            detail=(
                "حداقل یک پروتکل "
                "انتخاب کنید"
            ),
        )

    not_in_plan = [
        key
        for key in protocols
        if not bool(
            getattr(
                plan,
                field_map[key],
                False,
            )
        )
    ]

    if not_in_plan:
        raise HTTPException(
            status_code=422,
            detail=(
                "این پروتکل‌ها در پلن "
                "فعال نیستند: "
                + ", ".join(
                    not_in_plan
                )
            ),
        )

    unsupported = [
        key
        for key in protocols
        if not any(
            bool(
                getattr(
                    node,
                    field_map[key],
                    False,
                )
            )
            for node in nodes
        )
    ]

    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=(
                "سرورهای انتخابی این "
                "پروتکل‌ها را ندارند: "
                + ", ".join(
                    unsupported
                )
            ),
        )

    desired_protocols = set(
        protocols
    )

    desired_node_ids = set(
        node_ids
    )

    # ------------------------------------------------------
    # Store desired subscription state
    # ------------------------------------------------------

    sub.plan_id = plan.id
    sub.traffic_limit_bytes = (
        new_limit
    )

    # TWINPANEL_ADMIN_ACCOUNT_CREDENTIAL_EDIT_V1
    # Optional account credentials supplied by the admin edit form.
    # Missing fields mean "keep current value".
    old_account_username = str(
        sub.account_username
        or _safe_username(
            sub,
            user,
        )
        or ""
    ).strip()

    old_account_password = str(
        sub.account_password_encrypted
        or ""
    )

    account_username_changed = False
    account_password_changed = False

    if "account_username" in payload:

        requested_username = str(
            payload.get(
                "account_username"
            )
            or ""
        ).strip()

        if not requested_username:
            raise HTTPException(
                status_code=422,
                detail="نام کاربری نمی‌تواند خالی باشد",
            )

        if (
            len(requested_username) > 120
            or not re.fullmatch(
                r"[A-Za-z0-9_.-]+",
                requested_username,
            )
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "نام کاربری فقط می‌تواند شامل "
                    "حروف انگلیسی، عدد، نقطه، خط تیره "
                    "و زیرخط باشد"
                ),
            )

        account_username_changed = (
            requested_username
            != old_account_username
        )

        sub.account_username = (
            requested_username
        )

    if "account_password" in payload:

        requested_password = str(
            payload.get(
                "account_password"
            )
            or ""
        ).strip()

        if not requested_password:
            raise HTTPException(
                status_code=422,
                detail="رمز عبور نمی‌تواند خالی باشد",
            )

        if (
            len(requested_password) < 4
            or len(requested_password) > 128
            or any(
                ch.isspace()
                for ch in requested_password
            )
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "رمز عبور باید بین ۴ تا ۱۲۸ "
                    "کاراکتر و بدون فاصله باشد"
                ),
            )

        account_password_changed = (
            requested_password
            != old_account_password
        )

        sub.account_password_encrypted = (
            requested_password
        )

    account_credentials_changed = (
        account_username_changed
        or account_password_changed
    )

    # TWINPANEL_EXIT_MIGRATION_ENFORCEMENT_V2
    _removed_node_ids = sorted(
        old_node_ids - desired_node_ids
    )

    _removed_exit_node_ids = [
        int(_n.id)
        for _n in (
            db.query(Node).filter(Node.retired_at.is_(None))
            .filter(
                Node.id.in_(_removed_node_ids)
            )
            .all()
            if _removed_node_ids
            else []
        )
        if str(
            getattr(
                _n.node_type,
                "value",
                _n.node_type,
            )
        ) == "exit"
    ]

    if _removed_exit_node_ids:
        from ..subscription_enforcement import (
            queue_subscription_enforcement
            as _queue_exit_change,
        )

        _queue_exit_change(
            db,
            sub,
            command_type="revoke_subscription",
            reason="exit_node_removed",
            protocols=sorted(old_protocols),
            node_ids=_removed_exit_node_ids,
        )
    (
        db.query(SubscriptionNode)
        .filter(
            SubscriptionNode.subscription_id
            == sub.id
        )
        .delete(
            synchronize_session=False
        )
    )

    for node_id in node_ids:
        db.add(
            SubscriptionNode(
                subscription_id=sub.id,
                node_id=node_id,
            )
        )

    # TWINPANEL_PROTOCOL_REMOVAL_ENFORCEMENT_V1
    _twinpanel_removed_protocols = sorted(
        old_protocols
        - set(protocols)
    )

    if _twinpanel_removed_protocols:
        queue_subscription_enforcement(
            db,
            sub,
            command_type=
                "revoke_subscription",
            reason=
                "protocol_removed",
            protocols=
                _twinpanel_removed_protocols,
            node_ids=
                sorted(old_node_ids),
        )

    (
        db.query(SubscriptionProtocol)
        .filter(
            SubscriptionProtocol.subscription_id
            == sub.id
        )
        .delete(
            synchronize_session=False
        )
    )

    for key in protocols:
        db.add(
            SubscriptionProtocol(
                subscription_id=sub.id,
                protocol=key,
            )
        )

    # Compatibility columns.
    # These are no longer access-control fields. Keep one Iran
    # and one Exit reference only for legacy code paths.
    sub.iran_node_id = next(
        (
            node.id
            for node in nodes
            if node.node_type == NodeType.IRAN
        ),
        None,
    )

    sub.exit_node_id = next(
        (
            node.id
            for node in nodes
            if node.node_type == NodeType.EXIT
        ),
        None,
    )

    db.flush()

    # ------------------------------------------------------
    # Disable removed protocols
    # Keep secrets/config so re-enabling does not rotate keys.
    # ------------------------------------------------------

    removed_protocols = (
        old_protocols
        - desired_protocols
    )

    if removed_protocols:
        (
            db.query(
                ProtocolCredential
            )
            .filter(
                ProtocolCredential.subscription_id
                == sub.id,
                ProtocolCredential.protocol.in_(
                    list(
                        removed_protocols
                    )
                ),
            )
            .update(
                {
                    ProtocolCredential.is_active:
                    False
                },
                synchronize_session=False,
            )
        )

    # ------------------------------------------------------
    # Credential reconcile
    #
    # Existing protocol/node pair:
    #   preserve exactly as-is.
    #
    # Missing protocol/node pair:
    #   provision only that pair.
    #
    # This avoids rotating existing OpenVPN/WireGuard keys.
    # ------------------------------------------------------

    username = (
        sub.account_username
        or _safe_username(
            sub,
            user,
        )
    )

    password = (
        sub.account_password_encrypted
        or _numeric_secret(8)
    )

    provision_errors = []
    created_pairs = []
    reused_pairs = []

    for protocol in protocols:

        desired_nodes = [
            node
            for node in nodes
            if bool(
                getattr(
                    node,
                    field_map[protocol],
                    False,
                )
            )
        ]

        cred = (
            db.query(
                ProtocolCredential
            )
            .filter(
                ProtocolCredential.subscription_id
                == sub.id,
                ProtocolCredential.protocol
                == protocol,
            )
            .first()
        )

        if not cred:
            cred = ProtocolCredential(
                subscription_id=sub.id,
                protocol=protocol,
            )
            db.add(cred)
            db.flush()

        decoded = (
            _dec(
                cred.config_text_encrypted
            )
            if cred.config_text_encrypted
            else []
        )

        if isinstance(decoded, list):
            existing_items = [
                item
                for item in decoded
                if isinstance(
                    item,
                    dict,
                )
            ]
        elif isinstance(decoded, dict):
            existing_items = [
                decoded
            ]
        else:
            existing_items = []

        existing_by_node = {}

        for item in existing_items:
            try:
                item_node_id = int(
                    item.get(
                        "node_id"
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            existing_by_node[
                item_node_id
            ] = item

        items = []

        # Reuse one existing V2Ray UUID
        # across newly added Exit nodes.
        xray_id = None

        if protocol == "v2ray":
            for item in existing_items:
                candidate = str(
                    item.get("uuid")
                    or ""
                ).strip()

                if candidate:
                    xray_id = candidate
                    break

            if not xray_id:
                xray_id = str(
                    uuid.uuid4()
                )

        for node in desired_nodes:

            existing = existing_by_node.get(
                int(node.id)
            )

            if existing:

                # TWINPANEL_ADMIN_SIMPLE_CREDENTIAL_SYNC_V1
                # Cisco and L2TP use the shared account username/password.
                # When an admin changes either value, update the real
                # server-side account instead of merely changing the DB.
                if (
                    account_credentials_changed
                    and protocol in {
                        "cisco",
                        "l2tp",
                    }
                ):
                    try:

                        if protocol == "cisco":
                            item = await _cisco(
                                db,
                                node,
                                sub,
                                user,
                                username,
                                password,
                            )

                        else:
                            item = await _l2tp(
                                db,
                                node,
                                sub,
                                user,
                                username,
                                password,
                            )

                    except Exception as exc:
                        # Preserve the old delivered item if updating
                        # this node failed. The API will expose the
                        # provisioning error to the admin.
                        items.append(
                            existing
                        )

                        provision_errors.append(
                            {
                                "protocol":
                                protocol,
                                "node_id":
                                int(node.id),
                                "node":
                                node.name,
                                "error":
                                (
                                    "credential update failed: "
                                    + str(exc)
                                ),
                            }
                        )

                        continue

                    # New credentials are live. If the username changed,
                    # retire the previous username afterwards so a failed
                    # create cannot lock the customer out.
                    if (
                        account_username_changed
                        and old_account_username
                        and old_account_username
                        != username
                    ):
                        cleanup_conn = None

                        try:
                            cleanup_conn = (
                                await ssh_connect_saved(
                                    node,
                                    db,
                                )
                            )

                            if protocol == "cisco":

                                await cmd(
                                    cleanup_conn,
                                    (
                                        "ocpasswd "
                                        "-c /etc/ocserv/ocpasswd "
                                        "-d "
                                        + shlex.quote(
                                            old_account_username
                                        )
                                        + " || true"
                                    ),
                                )

                            else:

                                escaped_old_username = (
                                    re.escape(
                                        old_account_username
                                    )
                                )

                                await cmd(
                                    cleanup_conn,
                                    (
                                        "grep -v '^"
                                        + escaped_old_username
                                        + "[[:space:]]' "
                                        "/etc/ppp/chap-secrets "
                                        "> /tmp/mvchap-edit.$$ "
                                        "|| true; "
                                        "cat /tmp/mvchap-edit.$$ "
                                        "> /etc/ppp/chap-secrets; "
                                        "rm -f /tmp/mvchap-edit.$$; "
                                        "chmod 600 "
                                        "/etc/ppp/chap-secrets"
                                    ),
                                )

                        except Exception as exc:

                            provision_errors.append(
                                {
                                    "protocol":
                                    protocol,
                                    "node_id":
                                    int(node.id),
                                    "node":
                                    node.name,
                                    "error":
                                    (
                                        "old username cleanup failed: "
                                        + str(exc)
                                    ),
                                }
                            )

                        finally:

                            if cleanup_conn is not None:
                                cleanup_conn.close()

                                await (
                                    cleanup_conn
                                    .wait_closed()
                                )

                    items.append(
                        item
                    )

                    created_pairs.append(
                        {
                            "protocol":
                            protocol,
                            "node_id":
                            int(node.id),
                            "credential_update":
                            True,
                        }
                    )

                    continue

                items.append(
                    existing
                )

                reused_pairs.append(
                    {
                        "protocol":
                        protocol,
                        "node_id":
                        int(node.id),
                    }
                )

                continue

            try:
                if protocol == "cisco":
                    item = await _cisco(
                        db,
                        node,
                        sub,
                        user,
                        username,
                        password,
                    )

                elif protocol == "openvpn":
                    item = await _openvpn(
                        db,
                        node,
                        sub,
                        user,
                    )

                elif protocol == "wireguard":
                    item = await _wireguard(
                        db,
                        node,
                        sub,
                        user,
                    )

                elif protocol == "l2tp":
                    item = await _l2tp(
                        db,
                        node,
                        sub,
                        user,
                        username,
                        password,
                    )

                elif protocol == "v2ray":
                    item = await _xray(
                        db,
                        node,
                        sub,
                        user,
                        xray_id,
                    )

                else:
                    continue

                items.append(
                    item
                )

                created_pairs.append(
                    {
                        "protocol":
                        protocol,
                        "node_id":
                        int(node.id),
                    }
                )

            except Exception as exc:
                provision_errors.append(
                    {
                        "protocol":
                        protocol,
                        "node_id":
                        int(node.id),
                        "node":
                        node.name,
                        "error":
                        str(exc),
                    }
                )

        # Removed Exit nodes disappear from
        # the delivered credential payload.
        # Existing server-side cleanup will be
        # handled by the later reconciliation core.
        cred.config_text_encrypted = (
            _enc(items)
            if items
            else None
        )

        cred.is_active = bool(
            items
        )

        if protocol in {
            "cisco",
            "l2tp",
        }:
            cred.username = username
            cred.secret_encrypted = (
                _enc(
                    {
                        "password":
                        password
                    }
                )
            )

    _added_node_ids = sorted(
        desired_node_ids - old_node_ids
    )

    _added_exit_node_ids = {
        int(_n.id)
        for _n in (
            db.query(Node).filter(Node.retired_at.is_(None))
            .filter(
                Node.id.in_(_added_node_ids)
            )
            .all()
            if _added_node_ids
            else []
        )
        if str(
            getattr(
                _n.node_type,
                "value",
                _n.node_type,
            )
        ) == "exit"
    }

    if (
        _added_exit_node_ids
        and str(
            getattr(
                sub.status,
                "value",
                sub.status,
            )
        ) == "active"
    ):
        from ..subscription_enforcement import (
            queue_subscription_enforcement
            as _queue_exit_restore,
        )

        _good_pairs = (
            list(created_pairs)
            + list(reused_pairs)
        )

        for _exit_id in sorted(
            _added_exit_node_ids
        ):
            _restore_protocols = sorted({
                str(_pair.get("protocol") or "")
                for _pair in _good_pairs
                if (
                    int(
                        _pair.get(
                            "node_id",
                            0,
                        )
                    )
                    == _exit_id
                    and str(
                        _pair.get(
                            "protocol",
                        )
                        or ""
                    )
                )
            })

            if _restore_protocols:
                _queue_exit_restore(
                    db,
                    sub,
                    command_type="restore_subscription",
                    reason="exit_node_added",
                    protocols=_restore_protocols,
                    node_ids=[_exit_id],
                )
    db.commit()
    db.refresh(sub)

    return {
        "ok":
            len(provision_errors) == 0,

        "subscription_id":
            sub.id,

        "added_protocols":
            sorted(
                desired_protocols
                - old_protocols
            ),

        "removed_protocols":
            sorted(
                old_protocols
                - desired_protocols
            ),

        "added_nodes":
            sorted(
                desired_node_ids
                - old_node_ids
            ),

        "removed_nodes":
            sorted(
                old_node_ids
                - desired_node_ids
            ),

        "created_pairs":
            created_pairs,

        "reused_pairs":
            reused_pairs,

        "provision_errors":
            provision_errors,
    }


