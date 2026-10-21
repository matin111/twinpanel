from __future__ import annotations

import base64
import json
import re
import shlex
from dataclasses import dataclass
from typing import Any

from .models import Node
from .routers.provision import active, cmd, listener, ufw_allow


SERVICE_NAME = "twinpanel-sing-box"
CONFIG_DIR = "/etc/twinpanel/sing-box"
CONFIG_PATH = f"{CONFIG_DIR}/config.json"
CERT_PATH = f"{CONFIG_DIR}/server.crt"
KEY_PATH = f"{CONFIG_DIR}/server.key"
STATE_PATH = f"{CONFIG_DIR}/bootstrap.json"


@dataclass(frozen=True)
class ModernProtocolSpec:
    key: str
    title: str
    transport: str
    default_port: int
    inbound_type: str
    tag: str


MODERN_PROTOCOL_SPECS: dict[str, ModernProtocolSpec] = {
    "hysteria2": ModernProtocolSpec(
        key="hysteria2",
        title="Hysteria2",
        transport="udp",
        default_port=8444,
        inbound_type="hysteria2",
        tag="twinpanel-hysteria2-in",
    ),
    "tuic": ModernProtocolSpec(
        key="tuic",
        title="TUIC v5",
        transport="udp",
        default_port=8445,
        inbound_type="tuic",
        tag="twinpanel-tuic-in",
    ),
    "anytls": ModernProtocolSpec(
        key="anytls",
        title="AnyTLS",
        transport="tcp",
        default_port=8446,
        inbound_type="anytls",
        tag="twinpanel-anytls-in",
    ),
}


class ModernProtocolError(RuntimeError):
    pass


def supported_protocols() -> list[dict[str, Any]]:
    return [
        {
            "key": spec.key,
            "title": spec.title,
            "transport": spec.transport,
            "default_port": spec.default_port,
            "core": "sing-box",
            "service": SERVICE_NAME,
        }
        for spec in MODERN_PROTOCOL_SPECS.values()
    ]


def normalize_protocols(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for raw in values or []:
        key = str(raw or "").strip().lower()
        if key not in MODERN_PROTOCOL_SPECS:
            raise ModernProtocolError(f"Unsupported modern protocol: {key or raw}")
        if key not in result:
            result.append(key)
    if not result:
        raise ModernProtocolError("At least one modern protocol is required")
    return result


def normalized_ports(
    protocols: list[str],
    values: dict[str, int] | None,
) -> dict[str, int]:
    supplied = values or {}
    result: dict[str, int] = {}
    used: set[int] = set()
    for key in protocols:
        spec = MODERN_PROTOCOL_SPECS[key]
        try:
            port = int(supplied.get(key, spec.default_port))
        except (TypeError, ValueError):
            raise ModernProtocolError(f"Invalid port for {key}") from None
        if not 1 <= port <= 65535:
            raise ModernProtocolError(f"Port for {key} must be between 1 and 65535")
        if port in used:
            raise ModernProtocolError("Modern protocols cannot share the same listen port")
        used.add(port)
        result[key] = port
    return result


def _safe_cert_name(node: Node) -> tuple[str, list[str]]:
    domain = str(getattr(node, "public_domain", None) or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/", 1)[0].split(":", 1)[0]
    public_ip = str(getattr(node, "public_ip", "") or "").strip()

    san: list[str] = []
    if domain and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain):
        san.append(f"DNS:{domain}")
    if public_ip:
        san.append(f"IP:{public_ip}")

    common_name = domain or public_ip
    if not common_name:
        raise ModernProtocolError("Node has no usable public domain or IP for TLS identity")
    return common_name, san


def _bootstrap_script(
    protocols: list[str],
    ports: dict[str, int],
) -> str:
    desired = {
        key: {
            "type": MODERN_PROTOCOL_SPECS[key].inbound_type,
            "tag": MODERN_PROTOCOL_SPECS[key].tag,
            "port": ports[key],
        }
        for key in protocols
    }

    return f'''from __future__ import annotations
import json
import os
import secrets
import uuid

CONFIG = {CONFIG_PATH!r}
STATE = {STATE_PATH!r}
CERT = {CERT_PATH!r}
KEY = {KEY_PATH!r}
DESIRED = {desired!r}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value
    except FileNotFoundError:
        return default


state = load_json(STATE, {{}})
if not isinstance(state, dict):
    state = {{}}


def token(size=32):
    return secrets.token_urlsafe(size)


def ensure_seed(name):
    seed = state.get(name)
    if not isinstance(seed, dict):
        seed = {{}}
    if name == "tuic":
        seed.setdefault("uuid", str(uuid.uuid4()))
        seed.setdefault("password", token(24))
    else:
        seed.setdefault("password", token(32))
    state[name] = seed
    return seed


def new_inbound(name, spec):
    seed = ensure_seed(name)
    tls = {{
        "enabled": True,
        "certificate_path": CERT,
        "key_path": KEY,
    }}
    base = {{
        "type": spec["type"],
        "tag": spec["tag"],
        "listen": "0.0.0.0",
        "listen_port": int(spec["port"]),
        "tls": tls,
    }}
    if name == "hysteria2":
        base["users"] = [{{
            "name": "twinpanel-bootstrap",
            "password": seed["password"],
        }}]
    elif name == "tuic":
        base["users"] = [{{
            "name": "twinpanel-bootstrap",
            "uuid": seed["uuid"],
            "password": seed["password"],
        }}]
        base["congestion_control"] = "cubic"
        base["zero_rtt_handshake"] = False
        base["heartbeat"] = "10s"
    elif name == "anytls":
        base["users"] = [{{
            "name": "twinpanel-bootstrap",
            "password": seed["password"],
        }}]
    return base


doc = load_json(CONFIG, {{}})
if not isinstance(doc, dict):
    raise SystemExit("existing sing-box config is not an object")

inbounds = doc.get("inbounds")
if not isinstance(inbounds, list):
    inbounds = []

by_tag = {{
    item.get("tag"): item
    for item in inbounds
    if isinstance(item, dict) and item.get("tag")
}}

for name, spec in DESIRED.items():
    existing = by_tag.get(spec["tag"])
    fresh = new_inbound(name, spec)
    if isinstance(existing, dict) and existing.get("type") == spec["type"]:
        users = existing.get("users")
        if isinstance(users, list) and users:
            fresh["users"] = users
        if name == "hysteria2":
            for field in ("obfs", "up_mbps", "down_mbps", "ignore_client_bandwidth", "masquerade", "bbr_profile"):
                if field in existing:
                    fresh[field] = existing[field]
        elif name == "tuic":
            for field in ("congestion_control", "auth_timeout", "heartbeat"):
                if field in existing:
                    fresh[field] = existing[field]
            fresh["zero_rtt_handshake"] = False
        elif name == "anytls" and "padding_scheme" in existing:
            fresh["padding_scheme"] = existing["padding_scheme"]
        existing.clear()
        existing.update(fresh)
    else:
        inbounds.append(fresh)
        by_tag[spec["tag"]] = fresh

# Keep only one canonical direct outbound while preserving unrelated outbounds.
outbounds = doc.get("outbounds")
if not isinstance(outbounds, list):
    outbounds = []
if not any(isinstance(item, dict) and item.get("tag") == "direct" for item in outbounds):
    outbounds.append({{"type": "direct", "tag": "direct"}})

# Stable defaults, intentionally without DNS/routing overrides so the core
# cannot change the host's existing networking policy.
doc["log"] = doc.get("log") if isinstance(doc.get("log"), dict) else {{"level": "warn"}}
doc["inbounds"] = inbounds
doc["outbounds"] = outbounds

os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
with open(CONFIG + ".new", "w", encoding="utf-8") as handle:
    json.dump(doc, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")
with open(STATE + ".new", "w", encoding="utf-8") as handle:
    json.dump(state, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")
os.replace(STATE + ".new", STATE)
os.chmod(STATE, 0o600)
'''


def _remove_script(protocol: str) -> str:
    spec = MODERN_PROTOCOL_SPECS[protocol]
    return f'''from __future__ import annotations
import json
import os

path = {CONFIG_PATH!r}
tag = {spec.tag!r}
with open(path, "r", encoding="utf-8") as handle:
    doc = json.load(handle)
inbounds = doc.get("inbounds") if isinstance(doc, dict) else None
if not isinstance(inbounds, list):
    raise SystemExit("invalid sing-box config")
doc["inbounds"] = [
    item for item in inbounds
    if not (isinstance(item, dict) and item.get("tag") == tag)
]
with open(path + ".new", "w", encoding="utf-8") as handle:
    json.dump(doc, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")
print("remaining_inbounds=" + str(len(doc["inbounds"])))
'''


async def _ensure_core_and_certificate(conn, node: Node) -> dict[str, str]:
    common_name, sans = _safe_cert_name(node)
    san_text = ",".join(sans) or f"DNS:{common_name}"

    install_script = f'''set -eu
export DEBIAN_FRONTEND=noninteractive
mkdir -p /etc/apt/keyrings {shlex.quote(CONFIG_DIR)}
chmod 700 {shlex.quote(CONFIG_DIR)}
if ! command -v sing-box >/dev/null 2>&1; then
  curl -fsSL https://sing-box.app/gpg.key -o /etc/apt/keyrings/sagernet.asc
  chmod a+r /etc/apt/keyrings/sagernet.asc
  cat > /etc/apt/sources.list.d/sagernet.sources <<'EOF'
Types: deb
URIs: https://deb.sagernet.org/
Suites: *
Components: *
Enabled: yes
Signed-By: /etc/apt/keyrings/sagernet.asc
EOF
  apt-get update -y >/dev/null
  apt-get -o DPkg::Lock::Timeout=300 install -y sing-box openssl ca-certificates >/dev/null
fi
command -v openssl >/dev/null 2>&1 || apt-get -o DPkg::Lock::Timeout=300 install -y openssl >/dev/null
ln -sf "$(command -v sing-box)" /usr/local/bin/twinpanel-sing-box
if [ ! -s {shlex.quote(CERT_PATH)} ] || [ ! -s {shlex.quote(KEY_PATH)} ]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -sha256 -nodes -days 3650 \
    -subj {shlex.quote('/CN=' + common_name)} \
    -addext {shlex.quote('subjectAltName=' + san_text)} \
    -keyout {shlex.quote(KEY_PATH)} -out {shlex.quote(CERT_PATH)} >/dev/null 2>&1
fi
chmod 600 {shlex.quote(KEY_PATH)}
chmod 644 {shlex.quote(CERT_PATH)}
'''
    await cmd(conn, install_script, timeout=900)

    version = (await cmd(conn, "sing-box version | head -n1", check=False)).strip()
    pin = (
        await cmd(
            conn,
            f"openssl x509 -in {shlex.quote(CERT_PATH)} -pubkey -noout | "
            "openssl pkey -pubin -outform der 2>/dev/null | "
            "openssl dgst -sha256 -binary | openssl enc -base64 -A",
        )
    ).strip()
    return {"version": version, "certificate_public_key_sha256": pin}


async def install_protocols(
    conn,
    node: Node,
    protocols: list[str],
    ports: dict[str, int],
) -> dict[str, Any]:
    protocols = normalize_protocols(protocols)
    ports = normalized_ports(protocols, ports)
    core = await _ensure_core_and_certificate(conn, node)

    merge = _bootstrap_script(protocols, ports)
    merge_b64 = base64.b64encode(merge.encode()).decode()
    await cmd(
        conn,
        f"printf '%s' {shlex.quote(merge_b64)} | base64 -d | python3 && "
        f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.new')} && "
        f"if [ -s {shlex.quote(CONFIG_PATH)} ]; then cp -a {shlex.quote(CONFIG_PATH)} {shlex.quote(CONFIG_PATH)}.bak-$(date +%Y%m%d-%H%M%S); fi && "
        f"mv {shlex.quote(CONFIG_PATH + '.new')} {shlex.quote(CONFIG_PATH)} && chmod 600 {shlex.quote(CONFIG_PATH)}",
        timeout=120,
    )

    service = '''[Unit]
Description=TwinPanel Modern VPN Core (sing-box)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/twinpanel-sing-box run -c /etc/twinpanel/sing-box/config.json
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
'''
    service_b64 = base64.b64encode(service.encode()).decode()
    await cmd(
        conn,
        f"printf '%s' {shlex.quote(service_b64)} | base64 -d > /etc/systemd/system/{SERVICE_NAME}.service.new && "
        f"mv /etc/systemd/system/{SERVICE_NAME}.service.new /etc/systemd/system/{SERVICE_NAME}.service && "
        "systemctl daemon-reload && "
        f"systemctl enable {SERVICE_NAME}.service >/dev/null && systemctl restart {SERVICE_NAME}.service",
        timeout=120,
    )

    for key in protocols:
        spec = MODERN_PROTOCOL_SPECS[key]
        await ufw_allow(conn, ports[key], spec.transport)

    results: dict[str, Any] = {}
    for key in protocols:
        results[key] = await protocol_health(conn, key, ports[key])
    return {"core": core, "protocols": results}


async def protocol_health(conn, protocol: str, port: int | None = None) -> dict[str, Any]:
    if protocol not in MODERN_PROTOCOL_SPECS:
        raise ModernProtocolError(f"Unsupported modern protocol: {protocol}")
    spec = MODERN_PROTOCOL_SPECS[protocol]
    listen_port = int(port or spec.default_port)
    service_ok = await active(conn, SERVICE_NAME)
    listen_ok = await listener(conn, listen_port, spec.transport)
    return {
        "ok": bool(service_ok and listen_ok),
        "protocol": protocol,
        "name": spec.title,
        "service": SERVICE_NAME,
        "service_active": bool(service_ok),
        "listener": bool(listen_ok),
        "port": listen_port,
        "transport": spec.transport,
    }


async def certificate_pin(conn) -> str | None:
    value = (
        await cmd(
            conn,
            f"test -s {shlex.quote(CERT_PATH)} && "
            f"openssl x509 -in {shlex.quote(CERT_PATH)} -pubkey -noout | "
            "openssl pkey -pubin -outform der 2>/dev/null | "
            "openssl dgst -sha256 -binary | openssl enc -base64 -A",
            check=False,
        )
    ).strip()
    return value or None


async def remove_protocol(conn, protocol: str) -> dict[str, Any]:
    if protocol not in MODERN_PROTOCOL_SPECS:
        raise ModernProtocolError(f"Unsupported modern protocol: {protocol}")

    exists = (
        await cmd(
            conn,
            f"test -s {shlex.quote(CONFIG_PATH)} && echo yes || true",
            check=False,
        )
    ).strip()
    if exists != "yes":
        return {"ok": True, "protocol": protocol, "removed": False, "remaining": 0}

    script_b64 = base64.b64encode(_remove_script(protocol).encode()).decode()
    output = await cmd(
        conn,
        f"printf '%s' {shlex.quote(script_b64)} | base64 -d | python3",
        timeout=60,
    )
    match = re.search(r"remaining_inbounds=(\d+)", output)
    remaining = int(match.group(1)) if match else 0

    if remaining:
        await cmd(
            conn,
            f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.new')} && "
            f"cp -a {shlex.quote(CONFIG_PATH)} {shlex.quote(CONFIG_PATH)}.bak-$(date +%Y%m%d-%H%M%S) && "
            f"mv {shlex.quote(CONFIG_PATH + '.new')} {shlex.quote(CONFIG_PATH)} && "
            f"systemctl restart {SERVICE_NAME}.service",
            timeout=120,
        )
    else:
        await cmd(
            conn,
            f"mv {shlex.quote(CONFIG_PATH + '.new')} {shlex.quote(CONFIG_PATH)} && "
            f"systemctl disable --now {SERVICE_NAME}.service >/dev/null 2>&1 || true",
            check=False,
        )

    return {"ok": True, "protocol": protocol, "removed": True, "remaining": remaining}
