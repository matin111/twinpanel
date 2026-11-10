from __future__ import annotations

import base64
import json
import os
import re
import shlex
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .deps import get_current_user, require_admin
from .models import (
    Node,
    NodeProtocolConfig,
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionProtocol,
    User,
)


router = APIRouter(
    prefix="/v1/xray-modern",
    tags=["xray-modern"],
)


# TWINPANEL_XRAY_MODERN_RUNTIME_V2
#
# Existing VLESS RAW/plain remains on the legacy Xray port for old links.
# New customer-facing profiles use separate listeners and never expose the
# legacy plain URI to newly provisioned credentials.
#
# Restricted-network compatibility order:
#   1. WebSocket + TLS (when a valid Exit domain/certificate exists)
#   2. XHTTP + REALITY (modern no-domain profile)
#   3. HTTPUpgrade + TLS (when TLS is available)
#   4. gRPC + REALITY (last-resort fallback)
#
# Xray supports VLESS over WS/XHTTP/HTTPUpgrade/gRPC. REALITY is compatible
# with XHTTP/gRPC, while WS/HTTPUpgrade use ordinary TLS.

XRAY_REALITY_TARGET = (
    os.getenv(
        "TWINPANEL_XRAY_REALITY_TARGET",
        "www.microsoft.com:443",
    ).strip()
    or "www.microsoft.com:443"
)

XRAY_REALITY_SERVER_NAME = (
    os.getenv(
        "TWINPANEL_XRAY_REALITY_SERVER_NAME",
        XRAY_REALITY_TARGET.split(":", 1)[0],
    ).strip()
    or XRAY_REALITY_TARGET.split(":", 1)[0]
)

PROFILE_XHTTP = "xhttp_reality"
PROFILE_GRPC = "grpc_reality"
PROFILE_WS = "websocket_tls"
PROFILE_HTTPUPGRADE = "httpupgrade_tls"

PROFILE_META: dict[str, dict[str, Any]] = {
    PROFILE_XHTTP: {
        "offset": 1,
        "public_base": 23100,
        "title": "VLESS XHTTP REALITY",
        "transport": "xhttp",
        "security": "reality",
        "recommended": True,
    },
    PROFILE_GRPC: {
        "offset": 2,
        "public_base": 23200,
        "title": "VLESS gRPC REALITY",
        "transport": "grpc",
        "security": "reality",
        "recommended": False,
    },
    PROFILE_WS: {
        "offset": 3,
        "public_base": 23300,
        "title": "VLESS WebSocket TLS",
        "transport": "websocket",
        "security": "tls",
        "recommended": True,
    },
    PROFILE_HTTPUPGRADE: {
        "offset": 4,
        "public_base": 23400,
        "title": "VLESS HTTPUpgrade TLS",
        "transport": "httpupgrade",
        "security": "tls",
        "recommended": False,
    },
}

_TLS_PROFILES = {
    PROFILE_WS,
    PROFILE_HTTPUPGRADE,
}

_originals: dict[str, Any] = {}
_runtime_applied = False


def _enum_value(value: Any) -> str:
    return str(
        getattr(value, "value", value)
        or ""
    ).strip().lower()


def _clean_domain(value: Any) -> str:
    domain = str(value or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/")[0].strip()

    if ":" in domain:
        domain = domain.split(":", 1)[0]

    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?",
        domain,
    ):
        return ""

    return domain


def _reality_server_names(state: dict[str, Any]) -> list[str]:
    """Preserve previously published SNI values during a REALITY target swap.

    New subscriptions receive only the primary, currently applied SNI; already
    issued links keep their original UUID, public key, short ID and SNI and
    remain valid until clients refresh their subscription link.  Do not accept
    arbitrary whitespace/wildcards or grow an unbounded acceptance list.
    """
    primary = (
        _clean_domain(state.get("reality_server_name"))
        or _clean_domain(XRAY_REALITY_SERVER_NAME)
    )
    if not primary or "." not in primary or ".." in primary:
        raise RuntimeError("REALITY primary server name is invalid")

    names = [primary]
    aliases = state.get("reality_legacy_server_names")
    if isinstance(aliases, list):
        for raw in aliases[:8]:
            alias = _clean_domain(raw)
            if alias and "." in alias and ".." not in alias and alias not in names:
                names.append(alias)
                if len(names) >= 5:
                    break
    return names


def _target_port(base_port: int, profile: str) -> int:
    port = int(base_port) + int(PROFILE_META[str(profile)]["offset"])

    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid Xray target port: {port}")

    return port


def _public_port(exit_node_id: int, profile: str) -> int:
    node_id = int(exit_node_id)

    if not 1 <= node_id <= 999:
        raise RuntimeError(
            "Xray modern public routing supports Exit IDs 1..999"
        )

    port = int(PROFILE_META[str(profile)]["public_base"]) + node_id

    if not 1 <= port <= 65535:
        raise RuntimeError(f"invalid Xray public port: {port}")

    return port


def _profile_endpoint(
    db: Session,
    node: Node,
    profile: str,
) -> tuple[str, int]:
    from .routers import account_delivery

    host, legacy_port = account_delivery._tunnel_access_endpoint(
        db,
        node,
        "v2ray",
    )

    base_port = account_delivery._port(
        db,
        node.id,
        "v2ray",
    )

    expected_tunnel_port = 23000 + int(node.id)

    # Active/assigned Iran ingress. Reuse the same logical tunnel and only
    # publish a different service port; transport internals stay hidden.
    if int(legacy_port) == expected_tunnel_port:
        return host, _public_port(node.id, profile)

    # No Iran assignment: preserve the existing direct-Exit fallback model.
    return host, _target_port(base_port, profile)


def _build_uri(
    *,
    profile: str,
    client_id: str,
    host: str,
    port: int,
    profile_name: str,
    state: dict[str, Any],
) -> str:
    query: list[tuple[str, str]] = [
        ("encryption", "none"),
    ]

    if profile == PROFILE_XHTTP:
        query.extend(
            [
                ("security", "reality"),
                ("type", "xhttp"),
                ("path", str(state["xhttp_path"])),
                # Explicit stream-one avoids recent client auto-mode
                # regressions while the server accepts stream-one via
                # stream-up compatibility.
                ("mode", "stream-one"),
                ("sni", str(state["reality_server_name"])),
                ("fp", "chrome"),
                ("pbk", str(state["reality_password"])),
                ("sid", str(state["short_id_xhttp"])),
            ]
        )

    elif profile == PROFILE_WS:
        domain = str(state.get("tls_domain") or "").strip()
        if not domain:
            raise RuntimeError("WebSocket TLS domain is unavailable")

        query.extend(
            [
                ("security", "tls"),
                ("type", "ws"),
                ("sni", str(state.get("tls_sni_ws") or domain)),
                ("host", str(state.get("tls_sni_ws") or domain)),
                ("path", str(state["ws_path"])),
                ("fp", "chrome"),
                ("alpn", "http/1.1"),
            ]
        )

    elif profile == PROFILE_HTTPUPGRADE:
        domain = str(state.get("tls_domain") or "").strip()
        if not domain:
            raise RuntimeError("HTTPUpgrade TLS domain is unavailable")

        query.extend(
            [
                ("security", "tls"),
                ("type", "httpupgrade"),
                ("sni", domain),
                ("host", domain),
                ("path", str(state["httpupgrade_path"])),
                ("fp", "chrome"),
                ("alpn", "http/1.1"),
            ]
        )

    else:
        raise RuntimeError(f"unknown Xray modern profile: {profile}")

    label = (
        str(profile_name)
        + "-"
        + str(PROFILE_META[profile]["title"]).replace(" ", "-")
    )

    return (
        f"vless://{client_id}@{host}:{int(port)}"
        f"?{urlencode(query)}"
        f"#{quote(label, safe='')}"
    )


def _state_generator_script(domain: str) -> str:
    return f'''
import json
import os
import pwd
import secrets
import shutil
import subprocess
from pathlib import Path

domain = {domain!r}
default_reality_target = {XRAY_REALITY_TARGET!r}
default_reality_server_name = {XRAY_REALITY_SERVER_NAME!r}

state_path = Path(
    "/usr/local/etc/xray/twinpanel-modern-state.json"
)
state = {{}}

if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("invalid Xray modern state: " + repr(exc))

# Even if an outdated caller drops the Node argument, never silently reset
# an existing TLS Exit to REALITY. The previous guard only detected TLS when
# 'domain' was non-empty, which was precisely the broken reinstall case.
if not domain and (
    state.get("tls_enabled")
    or state.get("managed_cert")
    or state.get("tls_domain")
    or state.get("tls_sni_ws")
    or state.get("tls_sni_tcp")
    or Path("/usr/local/etc/xray/twinpanel-tls/fullchain.pem").is_file()
):
    raise RuntimeError("XRAY_DEDICATED_TLS_NODE_CONTEXT_REQUIRED")

# The node's verified runtime values are authoritative. Reconciliation must
# never reset an admin-applied REALITY target/SNI to global process defaults.
reality_target = str(state.get("reality_target") or default_reality_target)
reality_server_name = str(state.get("reality_server_name") or default_reality_server_name)
# Preserve previously issued clients' SNI values across node reconciliation.
# This is only an acceptance alias, not a new credential/secret or client
# delivery field. Keep the list small, stable and strictly hostname-shaped.
import re
legacy_reality_names = []
legacy_raw = state.get("reality_legacy_server_names")
if isinstance(legacy_raw, list):
    for candidate in legacy_raw[:8]:
        name = str(candidate or "").strip().lower()
        if (
            4 <= len(name) <= 253
            and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])", name)
            and ".." not in name
            and "." in name
            and name != reality_server_name.lower()
            and name not in legacy_reality_names
        ):
            legacy_reality_names.append(name)
        if len(legacy_reality_names) >= 4:
            break


def parse_x25519(output):
    parsed = {{}}
    for raw in str(output or "").splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lower().replace(" ", "").replace("_", "")
        value = value.strip()
        if not value:
            continue
        if key in {{"privatekey", "private"}}:
            parsed["private_key"] = value
        elif key in {{"password", "publickey", "public", "password(publickey)"}}:
            parsed["password"] = value
    return parsed


private_key = str(state.get("reality_private_key") or "").strip()
password = str(state.get("reality_password") or "").strip()

if not private_key:
    result = subprocess.run(
        ["/usr/local/bin/xray", "x25519"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "xray x25519 failed: "
            + (result.stderr or result.stdout or "")
        )
    parsed = parse_x25519(result.stdout + "\\n" + result.stderr)
    private_key = str(parsed.get("private_key") or "").strip()
    password = str(parsed.get("password") or "").strip()

if private_key and not password:
    result = subprocess.run(
        ["/usr/local/bin/xray", "x25519", "-i", private_key],
        text=True,
        capture_output=True,
        check=False,
    )
    parsed = parse_x25519(result.stdout + "\\n" + result.stderr)
    password = str(parsed.get("password") or "").strip()

if not private_key or not password:
    raise RuntimeError("REALITY key generation/derivation failed")


def stable_hex(key, bytes_count):
    value = str(state.get(key) or "").strip().lower()
    expected = bytes_count * 2
    if (
        len(value) != expected
        or any(c not in "0123456789abcdef" for c in value)
    ):
        value = secrets.token_hex(bytes_count)
    return value


def stable_path(key, prefix):
    value = str(state.get(key) or "").strip()
    if (
        not value.startswith("/")
        or len(value) < 8
        or len(value) > 120
        or any(c.isspace() for c in value)
    ):
        value = "/" + prefix + "-" + secrets.token_hex(8)
    return value


short_id_xhttp = stable_hex("short_id_xhttp", 8)

xhttp_path = stable_path("xhttp_path", "xh")
ws_path = stable_path("ws_path", "ws")
httpupgrade_path = stable_path("httpupgrade_path", "hu")

tls_enabled = False
source_cert = ""
source_key = ""
managed_cert = ""
managed_key = ""
service_user = "root"

if domain:
    candidates = [
        (
            f"/etc/letsencrypt/live/{{domain}}/fullchain.pem",
            f"/etc/letsencrypt/live/{{domain}}/privkey.pem",
        ),
        (
            f"/root/.acme.sh/{{domain}}_ecc/fullchain.cer",
            f"/root/.acme.sh/{{domain}}_ecc/{{domain}}.key",
        ),
        (
            f"/root/.acme.sh/{{domain}}/fullchain.cer",
            f"/root/.acme.sh/{{domain}}/{{domain}}.key",
        ),
        # The panel's safe ACME relay may install the validated certificate
        # directly into Xray's managed TLS directory. Older reconciliation
        # ignored it, reset tls_enabled=False and rebuilt three REALITY
        # inbounds despite the certificate being valid and still on disk.
        (
            "/usr/local/etc/xray/twinpanel-tls/fullchain.pem",
            "/usr/local/etc/xray/twinpanel-tls/privkey.pem",
        ),
    ]

    for cert, key in candidates:
        if not (os.path.isfile(cert) and os.path.isfile(key)):
            continue
        valid = subprocess.run(
            ["openssl", "x509", "-checkend", "86400", "-noout", "-in", cert],
            text=True,
            capture_output=True,
            check=False,
        )
        host = subprocess.run(
            ["openssl", "x509", "-checkhost", domain, "-noout", "-in", cert],
            text=True,
            capture_output=True,
            check=False,
        )
        if (valid.returncode == 0 and host.returncode == 0
                and f"Hostname {{domain}} does match certificate" in host.stdout
                and "does NOT match" not in host.stdout):
            # Ensure the selected private key actually belongs to the
            # certificate. A stale domain/key pair must never be published.
            cert_public = subprocess.run(
                ["openssl", "x509", "-in", cert, "-pubkey", "-noout"],
                text=True, capture_output=True, check=False,
            )
            key_public = subprocess.run(
                ["openssl", "pkey", "-in", key, "-pubout"],
                text=True, capture_output=True, check=False,
            )
            if (cert_public.returncode or key_public.returncode
                    or cert_public.stdout != key_public.stdout):
                continue
            source_cert = cert
            source_key = key
            break

# Never downgrade a previously configured dedicated TLS Exit to Reality
# because ACME is temporarily unreachable or a certificate is missing.
# Fail *before* rewriting state or service configuration. Initial Exits
# without previous state are handled by their separate TLS preflight.
if domain and not source_cert and (
    state.get("tls_enabled") or state.get("managed_cert")
):
    raise RuntimeError("XRAY_DEDICATED_TLS_CERTIFICATE_MISSING_STOP")

if source_cert and source_key:
    user_result = subprocess.run(
        ["systemctl", "show", "xray.service", "-p", "User", "--value"],
        text=True,
        capture_output=True,
        check=False,
    )
    service_user = user_result.stdout.strip() or "root"

    target_dir = Path("/usr/local/etc/xray/twinpanel-tls")
    target_dir.mkdir(parents=True, exist_ok=True)
    managed_cert = str(target_dir / "fullchain.pem")
    managed_key = str(target_dir / "privkey.pem")

    if os.path.realpath(source_cert) != os.path.realpath(managed_cert):
        shutil.copyfile(source_cert, managed_cert)
    if os.path.realpath(source_key) != os.path.realpath(managed_key):
        shutil.copyfile(source_key, managed_key)
    os.chmod(managed_cert, 0o644)
    os.chmod(managed_key, 0o600)

    if service_user != "root":
        try:
            entry = pwd.getpwnam(service_user)
            os.chown(managed_cert, entry.pw_uid, entry.pw_gid)
            os.chown(managed_key, entry.pw_uid, entry.pw_gid)
        except KeyError:
            managed_cert = ""
            managed_key = ""

    tls_enabled = bool(managed_cert and managed_key)

state = {{
    "version": 2,
    "reality_private_key": private_key,
    "reality_password": password,
    "reality_target": reality_target,
    "reality_server_name": reality_server_name,
    "reality_legacy_server_names": legacy_reality_names,
    # Only explicitly opted-in nodes set BBR for Xray listener sockets.
    # Never change the host-wide TCP default or unrelated VPN processes.
    "vless_tcp_congestion": "bbr" if str(state.get("vless_tcp_congestion") or "").lower() == "bbr" else "",
    "tls_sni_tcp": str(state.get("tls_sni_tcp") or ""),
    "tls_sni_ws": str(state.get("tls_sni_ws") or ""),
    "short_id_xhttp": short_id_xhttp,
    "xhttp_path": xhttp_path,
    "ws_path": ws_path,
    "httpupgrade_path": httpupgrade_path,
    "tls_enabled": tls_enabled,
    "tls_domain": domain if tls_enabled else "",
    "source_cert": source_cert if tls_enabled else "",
    "source_key": source_key if tls_enabled else "",
    "managed_cert": managed_cert if tls_enabled else "",
    "managed_key": managed_key if tls_enabled else "",
    "service_user": service_user,
}}

state_path.parent.mkdir(parents=True, exist_ok=True)
tmp = state_path.with_suffix(".tmp")
tmp.write_text(
    json.dumps(state, ensure_ascii=False, indent=2) + "\\n",
    encoding="utf-8",
)
os.chmod(tmp, 0o600)
os.replace(tmp, state_path)
print(json.dumps(state, ensure_ascii=False, separators=(",", ":")))
'''


def _merge_clients_script() -> str:
    return r'''
import json
import os

old_path = "/usr/local/etc/xray/config.json"
new_path = "/usr/local/etc/xray/config.json.twinpanel-modern"

with open(new_path, "r", encoding="utf-8") as handle:
    new_doc = json.load(handle)

clients_by_id = {}
email_to_id = {}

if os.path.exists(old_path):
    with open(old_path, "r", encoding="utf-8") as handle:
        old_doc = json.load(handle)

    for inbound in old_doc.get("inbounds", []):
        if (
            not isinstance(inbound, dict)
            or inbound.get("protocol") != "vless"
        ):
            continue

        clients = inbound.get("settings", {}).get("clients", [])
        if not isinstance(clients, list):
            continue

        for client in clients:
            if not isinstance(client, dict):
                continue

            client_id = str(client.get("id") or "").strip()
            email = str(client.get("email") or "").strip()
            if not client_id:
                continue

            previous = clients_by_id.get(client_id)
            if (
                previous
                and str(previous.get("email") or "").strip() not in {"", email}
            ):
                raise RuntimeError("Xray duplicate UUID conflict")

            if email and email in email_to_id and email_to_id[email] != client_id:
                raise RuntimeError("Xray duplicate email conflict")

            item = {
                "id": client_id,
                "level": int(client.get("level") or 0),
            }
            if email:
                item["email"] = email

            clients_by_id[client_id] = item
            if email:
                email_to_id[email] = client_id

for inbound in new_doc.get("inbounds", []):
    if (
        not isinstance(inbound, dict)
        or inbound.get("protocol") != "vless"
    ):
        continue

    inbound.setdefault("settings", {})["clients"] = [
        dict(item)
        for item in clients_by_id.values()
    ]

with open(new_path, "w", encoding="utf-8") as handle:
    json.dump(new_doc, handle, ensure_ascii=False, indent=2)
    handle.write("\n")

print("preserved_clients=", len(clients_by_id))
'''


def _client_sync_script(client_id: str, email: str) -> str:
    """Build a node-local, idempotent VLESS client sync.

    An already present UUID/email must never rewrite config or restart Xray.
    Actual changes are staged atomically with original owner/group/mode kept.
    """
    return f'''
import json
import os
import stat
import tempfile
from pathlib import Path

path = Path("/usr/local/etc/xray/config.json")
with path.open("r", encoding="utf-8") as handle:
    doc = json.load(handle)

found = 0
changed = False
for inbound in doc.get("inbounds", []):
    if (
        not isinstance(inbound, dict)
        or inbound.get("protocol") != "vless"
    ):
        continue

    clients = inbound.setdefault("settings", {{}}).setdefault("clients", [])
    if not isinstance(clients, list):
        raise RuntimeError("invalid Xray VLESS client list")
    matching = [
        item for item in clients
        if isinstance(item, dict)
        and str(item.get("email") or "") == {email!r}
    ]
    if (
        len(matching) == 1
        and len(clients) == sum(isinstance(item, dict) for item in clients)
        and str(matching[0].get("id") or "") == {client_id!r}
        and int(matching[0].get("level") or 0) == 0
    ):
        found += 1
        continue

    clients[:] = [
        item
        for item in clients
        if (
            isinstance(item, dict)
            and str(item.get("email") or "") != {email!r}
        )
    ]
    clients.append({{
        "id": {client_id!r},
        "email": {email!r},
        "level": 0,
    }})
    found += 1
    changed = True

if found < 3:
    raise RuntimeError("modern Xray inbounds are incomplete")

if changed:
    metadata = path.stat()
    staged = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="tp-xray-client-",
            suffix=".json", dir=str(path.parent), delete=False,
        ) as handle:
            staged = Path(handle.name)
            json.dump(doc, handle, ensure_ascii=False, indent=2)
            handle.write("\\n")
        os.chown(staged, metadata.st_uid, metadata.st_gid)
        os.chmod(staged, stat.S_IMODE(metadata.st_mode))
        os.replace(staged, path)
        staged = None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)

print(json.dumps({{"changed": changed, "updated_inbounds": found}}, separators=(",", ":")))
'''

def _preferred_node_xray_domain(node: Node | None) -> str:
    """Prefer explicit Xray TLS identity even in unwrapped repair workers.

    The standalone installer originally read only node.public_domain. That
    silently replaced valid dedicated v2usa/v2fin certificates with the
    shared general node hostname when a worker bypassed the runtime proxy.
    """
    if node is None:
        return ""
    return _clean_domain(
        getattr(node, "xray_domain", None)
        or getattr(node, "public_domain", None)
    )


async def _ensure_modern_xray(
    conn,
    base_port: int,
    node: Node | None = None,
    *,
    bootstrap_done: bool = False,
) -> dict[str, Any]:
    import asyncio
    from .routers import provision

    base_port = int(base_port)

    if not bootstrap_done:
        ready = (
            await provision.cmd(
                conn,
                (
                    "if [ -x /usr/local/bin/xray ] "
                    "&& [ -s /usr/local/etc/xray/config.json ]; "
                    "then echo ready; else echo missing; fi"
                ),
                check=False,
            )
        ).strip()

        if ready != "ready":
            original = _originals.get("install_xray")
            if original is None:
                raise RuntimeError("legacy Xray installer unavailable")

            ok, error = await original(conn, base_port)
            if not ok:
                raise RuntimeError(error or "legacy Xray bootstrap failed")

    # Core fail-safe: do not depend on optional monkeypatch ordering.
    # A dedicated certificate must be preferred by *every* installer,
    # including detached workers that call this base function directly.
    domain = _preferred_node_xray_domain(node)

    state_script = _state_generator_script(domain)
    state_b64 = base64.b64encode(state_script.encode()).decode()
    state_raw = await provision.cmd(
        conn,
        f"printf '%s' {shlex.quote(state_b64)} | base64 -d | python3",
    )

    try:
        state = json.loads(state_raw.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(
            "cannot parse Xray modern state: " + repr(exc)
        ) from exc

    private_key = str(state.get("reality_private_key") or "").strip()
    if not private_key:
        raise RuntimeError("REALITY private key is empty")

    available_profiles = [PROFILE_XHTTP]
    if bool(state.get("tls_enabled")):
        available_profiles.append(PROFILE_WS)

    # Reuse installed Xray listeners instead of rebuilding ports used by sing-box.
    check_script = (
        "python3 - <<'PYXRAYCHECK'\n"
        "import json\n"
        "doc=json.load(open('/usr/local/etc/xray/config.json'))\n"
        "tags={str(i.get('tag')):i for i in doc.get('inbounds',[]) "
        "if isinstance(i,dict)}\n"
        "required={'vless-in','vless-xhttp-reality'}\n"
        "ok=required.issubset(tags) and all("
        "tags[k].get('protocol')=='vless' for k in required)\n"
        "print(json.dumps({'ready':bool(ok),"
        "'base_port':tags.get('vless-in',{}).get('port'),"
        "'tags':list(tags)}))\n"
        "PYXRAYCHECK"
    )
    raw = await provision.cmd(conn, check_script, check=False)
    try:
        installed = json.loads(raw.strip().splitlines()[-1])
    except (ValueError, IndexError):
        installed = {}
    if (
        installed.get("ready")
        and int(installed.get("base_port") or 0) == base_port
        and await provision.active(conn, "xray")
    ):
        installed_tags = set(installed.get("tags") or [])
        installed_profiles = [PROFILE_XHTTP]
        if state.get("tls_enabled"):
            if "vless-ws-tls" in installed_tags:
                installed_profiles.append(PROFILE_WS)
        state["available_profiles"] = installed_profiles
        state["base_port"] = base_port
        return state

    candidate_ports = [base_port] + [
        _target_port(base_port, profile)
        for profile in available_profiles
    ]

    for candidate in candidate_ports:
        occupied = (
            await provision.cmd(
                conn,
                (
                    "ss -H -lntp 2>/dev/null "
                    f"| awk '$4 ~ /:{int(candidate)}$/ {{print}}' "
                    "| head -1"
                ),
                check=False,
            )
        ).strip()

        if occupied and "xray" not in occupied.lower():
            raise RuntimeError(
                "Xray modern port collision "
                f"port={candidate} listener={occupied[:300]}"
            )

    reality_common = {
        "show": False,
        "target": str(state.get("reality_target") or XRAY_REALITY_TARGET),
        "xver": 0,
        "serverNames": _reality_server_names(state),
        "privateKey": private_key,
    }

    inbounds: list[dict[str, Any]] = [
        {
            "tag": "vless-in",
            "listen": "0.0.0.0",
            "port": base_port,
            "protocol": "vless",
            "settings": {
                "clients": [],
                "decryption": "none",
            },
            "streamSettings": {
                "network": "tcp",
                "security": "none",
            },
        },
        {
            "tag": "vless-xhttp-reality",
            "listen": "0.0.0.0",
            "port": _target_port(base_port, PROFILE_XHTTP),
            "protocol": "vless",
            "settings": {
                "clients": [],
                "decryption": "none",
            },
            "streamSettings": {
                "network": "xhttp",
                "security": "reality",
                **({"sockopt": {"tcpcongestion": "bbr"}} if state.get("vless_tcp_congestion") == "bbr" else {}),
                "xhttpSettings": {
                    "path": str(state["xhttp_path"]),
                    "mode": "stream-up",
                },
                "realitySettings": {
                    **reality_common,
                    "shortIds": [str(state["short_id_xhttp"])],
                },
            },
        },
    ]

    if PROFILE_WS in available_profiles:
        inbounds.append(
            {
                "tag": "vless-ws-tls",
                "listen": "0.0.0.0",
                "port": _target_port(base_port, PROFILE_WS),
                "protocol": "vless",
                "settings": {
                    "clients": [],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "tls",
                    **({"sockopt": {"tcpcongestion": "bbr"}} if state.get("vless_tcp_congestion") == "bbr" else {}),
                    "wsSettings": {
                        "path": str(state["ws_path"]),
                    },
                    "tlsSettings": {
                        "serverName": str(state.get("tls_sni_ws") or state["tls_domain"]),
                        "minVersion": "1.2",
                        "alpn": ["http/1.1"],
                        "certificates": [
                            {
                                "certificateFile": str(state["managed_cert"]),
                                "keyFile": str(state["managed_key"]),
                            }
                        ],
                    },
                },
            }
        )


    inbounds.append(
        {
            "tag": "api",
            "listen": "127.0.0.1",
            "port": 10085,
            "protocol": "dokodemo-door",
            "settings": {
                "address": "127.0.0.1",
            },
        }
    )

    config = {
        "log": {"loglevel": "warning"},
        "api": {
            "tag": "api",
            "services": [
                "HandlerService",
                "LoggerService",
                "StatsService",
            ],
        },
        "stats": {},
        "policy": {
            "levels": {
                "0": {
                    "statsUserUplink": True,
                    "statsUserDownlink": True,
                }
            },
            "system": {
                "statsInboundUplink": True,
                "statsInboundDownlink": True,
            },
        },
        "inbounds": inbounds,
        "outbounds": [
            {
                "protocol": "freedom",
                "tag": "direct",
            }
        ],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["api"],
                    "outboundTag": "api",
                }
            ]
        },
    }

    config_b64 = base64.b64encode(
        json.dumps(config, ensure_ascii=False).encode()
    ).decode()
    merge_b64 = base64.b64encode(_merge_clients_script().encode()).decode()

    temp_path = "/usr/local/etc/xray/config.json.twinpanel-modern"

    await provision.cmd(
        conn,
        (
            "mkdir -p /usr/local/etc/xray; "
            f"printf '%s' {shlex.quote(config_b64)} "
            f"| base64 -d > {shlex.quote(temp_path)}; "
            f"printf '%s' {shlex.quote(merge_b64)} "
            "| base64 -d | python3"
        ),
    )

    await provision.cmd(
        conn,
        (
            "/usr/local/bin/xray run -test "
            f"-config {shlex.quote(temp_path)}"
        ),
    )

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = (
        "/usr/local/etc/xray/"
        f"config.json.bak-modern-{stamp}"
    )

    restart_output = await provision.cmd(
        conn,
        (
            "if [ -f /usr/local/etc/xray/config.json ]; "
            f"then cp -a /usr/local/etc/xray/config.json {shlex.quote(backup_path)}; "
            "fi; "
            f"install -o root -g root -m 0644 {shlex.quote(temp_path)} "
            "/usr/local/etc/xray/config.json; "
            f"rm -f {shlex.quote(temp_path)}; "
            "systemctl enable xray >/dev/null; "
            "systemctl restart xray >/dev/null 2>&1 "
            "|| echo XRAY_RESTART_FAILED"
        ),
        # Preserve evidence even when systemctl returns a nonzero exit code.
        check=False,
    )
    restart_ok = "XRAY_RESTART_FAILED" not in str(restart_output)

    await asyncio.sleep(1)

    service_ok = await provision.active(conn, "xray")
    missing_listeners = []

    for candidate in candidate_ports:
        if not await provision.listener(conn, candidate, "tcp"):
            missing_listeners.append(candidate)

    if not (restart_ok and service_ok and not missing_listeners):
        # Capture the reason BEFORE restoring the previous configuration.
        # Only inspect systemd metadata and the listener table: journal excerpts
        # can contain customer identifiers or credentials and are intentionally
        # not exposed in API errors.
        diagnostics = "unavailable"
        try:
            diagnostics = (
                await provision.cmd(
                    conn,
                    "systemctl show xray.service "
                    "-p ActiveState -p SubState -p Result "
                    "-p ExecMainStatus -p NRestarts --no-pager",
                    check=False,
                    timeout=12,
                )
            ).strip().replace("\n", "; ")[:350]
        except Exception:
            pass
        # Reduce recent Xray journal entries to fixed error categories on the
        # node itself. Never return raw logs or attacker-controlled log text.
        failure_reason = "UNKNOWN"
        try:
            reason_script = (
                "python3 - <<'PYXRAYREASON'\n"
                "import subprocess\n"
                "p=subprocess.run(['journalctl','-u','xray.service',"
                "'--since','-90 seconds','--no-pager','-n','80',"
                "'--output=cat'],capture_output=True,text=True,timeout=8)\n"
                "s=p.stdout.lower()\n"
                "checks=[('ADDRESS_IN_USE',('address already in use','bind: address already in use')),"
                "('CERTIFICATE_ERROR',('failed to load certificate','certificate verify failed','no such file or directory: certificate')),"
                "('PERMISSION_DENIED',('permission denied','operation not permitted')),"
                "('INVALID_CONFIG',('failed to load config','failed to parse','invalid configuration')),"
                "('START_LIMIT',('start request repeated too quickly',))]\n"
                "print(next((name for name,words in checks "
                "if any(word in s for word in words)),'UNKNOWN'))\n"
                "PYXRAYREASON"
            )
            candidate_reason = str(
                await provision.cmd(conn, reason_script, check=False, timeout=12)
            ).strip().splitlines()[-1]
            if candidate_reason in {
                "ADDRESS_IN_USE", "CERTIFICATE_ERROR", "PERMISSION_DENIED",
                "INVALID_CONFIG", "START_LIMIT", "UNKNOWN",
            }:
                failure_reason = candidate_reason
        except Exception:
            pass
        rollback_result = "not_attempted"
        try:
            await provision.cmd(
                conn,
                (
                    f"if [ -f {shlex.quote(backup_path)} ]; "
                    f"then cp -a {shlex.quote(backup_path)} "
                    "/usr/local/etc/xray/config.json; "
                    "systemctl restart xray; "
                    "else exit 44; fi"
                ),
            )
            rollback_result = "restored"
        except Exception:
            rollback_result = "failed"
        raise RuntimeError(
            "XRAY_MODERN_START_VERIFICATION_FAILED "
            f"restart_ok={restart_ok} service_active={service_ok} "
            f"missing_tcp_ports={','.join(map(str, missing_listeners)) or 'none'} "
            f"systemd={diagnostics} reason={failure_reason} "
            f"rollback={rollback_result}"
        )

    for candidate in candidate_ports:
        await provision.ufw_allow(conn, candidate, "tcp")

    await provision.cmd(
        conn,
        (
            "mkdir -p /etc/twinpanel/managed-identities; "
            "chmod 700 /etc/twinpanel/managed-identities; "
            "touch /etc/twinpanel/managed-identities/v2ray-modern"
        ),
    )

    state["available_profiles"] = available_profiles
    state["base_port"] = base_port
    return state


async def _three_tls_inbounds_live(
    conn, base_port: int, node: Node | None,
) -> bool:
    """Read-only strict installed health: file, Xray API and real listeners.

    The prior generic readiness check trusted base + XHTTP only; its result
    caused Repair to skip missing WS/TCP TLS and claim successful installation.
    Never call an installer as part of this probe.
    """
    from .routers import provision
    from .central_xray_node_authority_v1 import read_node_public_authority

    dedicated = _clean_domain(
        getattr(node, "xray_domain", None) if node is not None else ""
    )
    if not dedicated:
        return False
    try:
        authority = await read_node_public_authority(conn)
        if (
            authority.get("tls_enabled") is not True
            or str(authority.get("tls_domain") or "").lower() != dedicated
            or set(authority.get("profiles") or ()) != {
                "websocket_tls", "xhttp_reality", "tcp_tls",
            }
        ):
            return False
        if not await provision.active(conn, "xray"):
            return False

        live_text = await provision.cmd(
            conn,
            "/usr/local/bin/xray api lsi "
            "--server=127.0.0.1:10085 -isOnlyTags=true -timeout=5",
            check=False,
        )
        live_tags = {
            str(entry.get("tag") or "")
            for entry in json.loads(str(live_text).strip()).get("inbounds", [])
            if isinstance(entry, dict)
        }
        required_tags = {
            "vless-ws-tls", "vless-xhttp-reality", "vless-tcp-tls",
        }
        if not required_tags.issubset(live_tags):
            return False

        for profile in ("websocket_tls", "xhttp_reality", "tcp_tls"):
            if not await provision.listener(
                conn, _target_port(int(base_port), profile), "tcp",
            ):
                return False
        return True
    except Exception:
        return False


async def _install_xray_modern(conn, port: int, node: Node | None = None):
    """Install or repair Xray with the selected node's TLS authority.

    Never run the destructive legacy bootstrap against an existing config.
    That bootstrap used to overwrite all three TLS inbounds, after which the
    node-less modern wrapper rebuilt domainless REALITY and Vision profiles.
    """
    from .routers import provision

    original = _originals.get("install_xray")
    if original is None:
        return False, "legacy Xray installer unavailable"

    port = int(port)
    dedicated = _clean_domain(
        getattr(node, "xray_domain", None) if node is not None else ""
    )
    existing = (
        await provision.cmd(
            conn,
            "if [ -s /usr/local/etc/xray/config.json ]; "
            "then echo present; else echo absent; fi",
            check=False,
        )
    ).strip() == "present"

    if existing and node is None:
        # Every existing installation requires a node ID/domain. Fail before
        # executing any state generator or replacing any config or clients.
        return False, "XRAY_REPAIR_NODE_CONTEXT_REQUIRED"

    if dedicated:
        from . import xray_modern_admin
        try:
            certificate_ready = await xray_modern_admin._certificate_available(
                conn, dedicated,
            )
        except Exception:
            certificate_ready = False
        if not certificate_ready:
            return False, "XRAY_DEDICATED_TLS_CERTIFICATE_NOT_READY"

    if existing and await _three_tls_inbounds_live(conn, port, node):
        # Strict live check; healthy nodes are left bit-for-bit untouched.
        return True, None

    if existing:
        # We can repair an existing Xray config only when the binary remains.
        # Its bootstrapper must NEVER replace a real customer config.
        binary_ready = (
            await provision.cmd(
                conn,
                "test -x /usr/local/bin/xray && echo ready || echo missing",
                check=False,
            )
        ).strip() == "ready"
        if not binary_ready:
            return False, "XRAY_EXISTING_CONFIG_REQUIRES_SAFE_BINARY_RECOVERY"
    else:
        if await provision.active(conn, "xray"):
            return False, "XRAY_RUNNING_WITHOUT_MANAGED_CONFIG_STOP"
        # Fresh, never-configured node only: legacy bootstrap installs the
        # verified Xray binary and basic service; modern provisioning below
        # then receives the actual Node and dedicated hostname.
        ok, error = await original(conn, port)
        if not ok:
            return ok, error

    try:
        await _ensure_modern_xray(
            conn, port, node, bootstrap_done=True,
        )
        if dedicated and not await _three_tls_inbounds_live(
            conn, port, node,
        ):
            return False, "XRAY_TLS_THREE_INBOUNDS_NOT_VERIFIED"
        return True, None
    except Exception as exc:
        return False, str(exc)[:1800]


async def _existing_ok_modern(conn, protocol: str, settings):
    original = _originals.get("existing_ok")

    if protocol != "v2ray":
        return await original(conn, protocol, settings)

    from .routers import provision

    base_port = int(settings.xray_port)
    if not await provision.active(conn, "xray"):
        return False

    for candidate in (
        base_port,
        _target_port(base_port, PROFILE_XHTTP),
    ):
        if not await provision.listener(conn, candidate, "tcp"):
            return False

    return True


def _existing_uuid(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""

    value = str(item.get("uuid") or "").strip()
    if value:
        return value

    uri = str(item.get("uri") or "").strip()
    match = re.match(r"^vless://([^@/?#]+)@", uri)
    return match.group(1) if match else ""


async def _xray_account_modern(
    db: Session,
    node: Node,
    sub: Subscription,
    user: User,
    client_id: str,
    *,
    reusable_connection: Any | None = None,
) -> dict[str, Any]:
    from .routers import account_delivery, provision

    owns_connection = reusable_connection is None
    conn = reusable_connection if reusable_connection is not None else await account_delivery.ssh_connect_saved(node, db)

    try:
        base_port = account_delivery._port(db, node.id, "v2ray")
        state = await _ensure_modern_xray(conn, base_port, node)

        email = f"mv-{sub.id}@twinpanel"
        sync_script = _client_sync_script(client_id, email)
        sync_b64 = base64.b64encode(sync_script.encode()).decode()

        sync_raw = await provision.cmd(
            conn,
            f"printf '%s' {shlex.quote(sync_b64)} | base64 -d | python3",
        )
        try:
            sync_result = json.loads(sync_raw.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise RuntimeError("Xray client sync result is invalid") from exc
        if int(sync_result.get("updated_inbounds") or 0) < 3:
            raise RuntimeError("Xray client sync did not cover all VLESS inbounds")
        if bool(sync_result.get("changed")):
            # The hot client script must have already updated the running
            # Xray HandlerService AND persisted the config. Never disconnect
            # thousands of active users to add one credential.
            if not bool(sync_result.get("hot_applied")):
                raise RuntimeError(
                    "Xray credential change was not hot-applied; "
                    "global Xray restart is forbidden for account provisioning"
                )

        if not await provision.active(conn, "xray"):
            raise RuntimeError("Xray service did not remain active")

        username_part = account_delivery._download_filename_part(
            sub.account_username
            or account_delivery._safe_username(sub, user),
            f"user{sub.id}",
        )
        country_part = account_delivery._country_download_name(node)
        profile_name = f"{username_part}-{country_part}"

        available = set(state.get("available_profiles") or [])
        order: list[str] = []

        if PROFILE_WS in available:
            order.append(PROFILE_WS)
        order.append(PROFILE_XHTTP)

        profiles = []
        for profile in order:
            if profile not in available:
                continue

            host, public_port = _profile_endpoint(db, node, profile)
            uri = _build_uri(
                profile=profile,
                client_id=client_id,
                host=host,
                port=public_port,
                profile_name=profile_name,
                state=state,
            )
            meta = PROFILE_META[profile]

            profiles.append(
                {
                    "id": profile,
                    "title": meta["title"],
                    "recommended": bool(meta["recommended"]),
                    "security": meta["security"],
                    "transport": meta["transport"],
                    "server": host,
                    "port": public_port,
                    "uri": uri,
                    "sni": (
                        state.get("tls_domain")
                        if profile in _TLS_PROFILES
                        else state.get("reality_server_name")
                    ),
                }
            )

        if not profiles:
            raise RuntimeError("no modern Xray profile is available")

        primary = profiles[0]
        return {
            "node_id": node.id,
            "node": node.name,
            "server": primary["server"],
            "server_ip": primary["server"],
            "port": primary["port"],
            "uuid": client_id,
            "profile": primary["id"],
            "security": primary["security"],
            "transport": primary["transport"],
            "uri": primary["uri"],
            "profiles": profiles,
            "tls_available": bool(state.get("tls_enabled")),
            "legacy_plain_preserved": True,
        }

    finally:
        if owns_connection:
            conn.close()
            await conn.wait_closed()


def _live_client_item_modern(
    db: Session,
    sub: Subscription,
    protocol: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    original = _originals["live_client_item"]
    result = original(db, sub, protocol, item)

    if (
        str(protocol or "").strip().lower() != "v2ray"
        or not isinstance(result, dict)
    ):
        return result

    profiles = result.get("profiles")
    if not isinstance(profiles, list):
        return result

    try:
        node_id = int(result.get("node_id"))
    except (TypeError, ValueError):
        return result

    node = db.get(Node, node_id)
    if not node or node.node_type != NodeType.EXIT:
        return result

    updated = []
    for raw in profiles:
        if not isinstance(raw, dict):
            continue

        profile = dict(raw)
        profile_id = str(profile.get("id") or "").strip()
        if profile_id not in PROFILE_META:
            updated.append(profile)
            continue

        host, port = _profile_endpoint(db, node, profile_id)
        profile["server"] = host
        profile["port"] = port

        uri = str(profile.get("uri") or "")
        if uri:
            profile["uri"] = re.sub(
                r"^(vless://[^@]+@)[^:/?#]+:\d+",
                rf"\g<1>{host}:{port}",
                uri,
                count=1,
            )

        updated.append(profile)

    if updated:
        result["profiles"] = updated
        primary = updated[0]
        result["server"] = primary.get("server")
        result["server_ip"] = primary.get("server")
        result["port"] = primary.get("port")
        if primary.get("uri"):
            result["uri"] = primary["uri"]

    return result


def _public_payload_modern(
    db: Session,
    sub: Subscription,
) -> dict[str, Any]:
    payload = _originals["public_payload"](db, sub)
    from .routers import account_delivery

    for credential in payload.get("credentials", []):
        if str(credential.get("protocol") or "").strip().lower() != "v2ray":
            continue

        items = credential.get("items")
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            profiles = item.get("profiles")
            if not isinstance(profiles, list):
                continue

            for profile in profiles:
                if isinstance(profile, dict) and profile.get("uri"):
                    profile["qr"] = account_delivery._qr_data_uri(
                        str(profile["uri"])
                    )

    return payload


def _service_routes_modern(
    db: Session,
    exit_node: Node,
    exit_tunnel_ip: str,
) -> list[dict]:
    routes = list(
        _originals["service_routes"](
            db,
            exit_node,
            exit_tunnel_ip,
        )
    )

    cfg = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == exit_node.id,
            NodeProtocolConfig.protocol == "v2ray",
        )
        .first()
    )

    if not cfg or _enum_value(cfg.status) != "online":
        return routes

    base_port = int(cfg.port or 8443)
    existing = {
        (
            str(route.get("protocol") or ""),
            int(route.get("public_port") or 0),
        )
        for route in routes
        if isinstance(route, dict)
    }

    for profile in (
        PROFILE_XHTTP,
        PROFILE_WS,
    ):
        public_port = _public_port(exit_node.id, profile)
        key = ("v2ray", public_port)
        if key in existing:
            continue

        routes.append(
            {
                "protocol": "v2ray",
                "profile": profile,
                "exit_node_id": int(exit_node.id),
                "public_port": public_port,
                "target_ip": exit_tunnel_ip,
                "target_port": _target_port(base_port, profile),
                "transport": "tcp",
                "client_subnet": None,
            }
        )

    return routes


def _modern_item_present(item: dict[str, Any]) -> bool:
    profiles = item.get("profiles")
    if not isinstance(profiles, list):
        return False

    ids = {
        str(profile.get("id") or "")
        for profile in profiles
        if isinstance(profile, dict)
    }
    return PROFILE_XHTTP in ids


def _normalize_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [
            dict(item)
            for item in raw
            if isinstance(item, dict)
        ]
    if isinstance(raw, dict):
        return [dict(raw)]
    return []


async def _ensure_subscription_modern(
    db: Session,
    sub: Subscription,
    *,
    force: bool = False,
) -> dict[str, Any]:
    from .routers import account_delivery

    selected_protocols = {
        str(row[0]).strip().lower()
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == sub.id)
            .all()
        )
    }

    if "v2ray" not in selected_protocols:
        return {
            "ok": True,
            "skipped": True,
            "reason": "v2ray_not_selected",
            "connection": account_delivery._stored_info(db, sub),
        }

    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == sub.id,
            ProtocolCredential.protocol == "v2ray",
        )
        .first()
    )

    existing_items = _normalize_items(
        account_delivery._dec(cred.config_text_encrypted)
        if cred
        else None
    )

    user = db.get(User, sub.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    nodes = []
    for node in (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
        )
        .order_by(Node.id.asc())
        .all()
    ):
        if not bool(getattr(node, "enable_v2ray", False)):
            continue

        cfg = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == node.id,
                NodeProtocolConfig.protocol == "v2ray",
            )
            .first()
        )
        if not cfg or _enum_value(cfg.status) != "online":
            continue
        nodes.append(node)

    if not nodes:
        raise HTTPException(
            status_code=409,
            detail="هیچ سرور خروجی Xray آنلاین برای این اشتراک وجود ندارد",
        )

    old_by_node: dict[int, dict[str, Any]] = {}
    for item in existing_items:
        try:
            item_node_id = int(item.get("node_id"))
        except (TypeError, ValueError):
            continue
        old_by_node[item_node_id] = item

    eligible_ids = {int(node.id) for node in nodes}
    modern_ids = {
        node_id
        for node_id, item in old_by_node.items()
        if _modern_item_present(item)
    }

    if not force and eligible_ids and eligible_ids <= modern_ids:
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_modern",
            "connection": account_delivery._stored_info(db, sub),
        }

    final_by_node = dict(old_by_node)
    migrated = []
    errors = []

    for node in nodes:
        if (
            not force
            and int(node.id) in modern_ids
        ):
            continue

        previous = old_by_node.get(int(node.id))
        client_id = _existing_uuid(previous) or str(uuid.uuid4())

        try:
            item = await _xray_account_modern(
                db,
                node,
                sub,
                user,
                client_id,
            )
            final_by_node[int(node.id)] = item
            migrated.append(int(node.id))
        except Exception as exc:
            errors.append(
                {
                    "node_id": int(node.id),
                    "node": node.name,
                    "error": str(exc)[:1200],
                }
            )

    if (
        not migrated
        and not any(
            _modern_item_present(item)
            for item in final_by_node.values()
        )
    ):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ساخت اتصال‌های جدید Xray ناموفق بود",
                "errors": errors,
            },
        )

    if not cred:
        cred = ProtocolCredential(
            subscription_id=sub.id,
            protocol="v2ray",
        )
        db.add(cred)

    ordered = [
        final_by_node[key]
        for key in sorted(final_by_node)
        if isinstance(final_by_node[key], dict)
    ]

    cred.config_text_encrypted = account_delivery._enc(ordered)
    cred.is_active = True
    db.commit()

    return {
        "ok": len(errors) == 0,
        "migrated_node_ids": migrated,
        "errors": errors,
        "connection": account_delivery._stored_info(db, sub),
    }


@router.post("/customer/{subscription_id}/ensure")
async def customer_ensure_modern_xray(
    subscription_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, subscription_id)

    if not sub or int(sub.user_id) != int(user.id):
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")

    if _enum_value(sub.status) != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")

    if sub.expires_at and sub.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=403, detail="اشتراک منقضی شده است")

    return await _ensure_subscription_modern(db, sub, force=False)


@router.post(
    "/admin/{subscription_id}/ensure",
    dependencies=[Depends(require_admin)],
)
async def admin_ensure_modern_xray(
    subscription_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    return await _ensure_subscription_modern(db, sub, force=bool(force))


def apply_xray_modern_runtime() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    from .routers import account_delivery, provision, tunnels

    _originals["install_xray"] = provision.install_xray
    _originals["existing_ok"] = provision.existing_ok
    _originals["xray_account"] = account_delivery._xray
    _originals["live_client_item"] = account_delivery._live_client_item
    _originals["public_payload"] = account_delivery._public_payload
    _originals["service_routes"] = tunnels._service_routes_for_exit

    provision.install_xray = _install_xray_modern
    provision.existing_ok = _existing_ok_modern
    account_delivery._xray = _xray_account_modern
    account_delivery._live_client_item = _live_client_item_modern
    account_delivery._public_payload = _public_payload_modern
    tunnels._service_routes_for_exit = _service_routes_modern

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_MODERN_RUNTIME_V2_ACTIVE "
        "profiles=websocket_tls,xhttp_reality "
        "legacy_plain_preserved=1 transport_ui_hidden=1",
        flush=True,
    )
