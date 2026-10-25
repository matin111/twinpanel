from __future__ import annotations

import base64
import json
import re
import shlex
from typing import Any

from .models import Node
from .modern_protocol_runtime import (
    CERT_PATH,
    CONFIG_DIR,
    CONFIG_PATH,
    KEY_PATH,
    SERVICE_NAME,
    STATE_PATH,
    _ensure_core_and_certificate,
)
from .protocol_catalog import PROTOCOL_CATALOG
from .routers.provision import active, cmd, listener, ufw_allow


# Protocol Studio intentionally targets the current sing-box feature set.
# Snell server support, Hysteria2 bbr_profile/Gecko and the newest server
# controls used by our presets require 1.14+; fail before mutating config when
# a node cannot be upgraded to that baseline.
MIN_SING_BOX_VERSION = (1, 14, 0)

SINGBOX_PROTOCOLS = {
    key
    for key, definition in PROTOCOL_CATALOG.items()
    if definition.get("adapter") == "sing-box"
    and definition.get("runtime_status") == "ready"
}

TAGS = {key: f"twinpanel-{key}-in" for key in SINGBOX_PROTOCOLS}
SHADOWTLS_INNER_TAG = "twinpanel-shadowtls-inner"
SHADOWTLS_INNER_METHOD = "aes-256-gcm"


class ModernRuntimeV2Error(RuntimeError):
    pass


def _transport(protocol: str) -> str:
    value = str(PROTOCOL_CATALOG[protocol].get("transport") or "tcp")
    if value in {"udp", "tcp"}:
        return value
    return "tcp"


def _version_tuple(raw: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", str(raw or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


async def _read_core_version(conn) -> tuple[str, tuple[int, int, int] | None]:
    raw = (await cmd(conn, "sing-box version | head -n1", check=False)).strip()
    return raw, _version_tuple(raw)


def _mutation_script(desired: list[dict[str, Any]]) -> str:
    payload = json.dumps(desired, ensure_ascii=False)
    return f'''from __future__ import annotations
import json
import os
import secrets
import uuid

CONFIG = {CONFIG_PATH!r}
STATE = {STATE_PATH!r}
CERT = {CERT_PATH!r}
KEY = {KEY_PATH!r}
DESIRED = json.loads({payload!r})
SHADOWTLS_INNER_TAG = {SHADOWTLS_INNER_TAG!r}
SHADOWTLS_INNER_METHOD = {SHADOWTLS_INNER_METHOD!r}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def token(size=32):
    return secrets.token_urlsafe(size)


state = load_json(STATE, {{}})
if not isinstance(state, dict):
    state = {{}}


def seed_for(name):
    seed = state.get(name)
    if not isinstance(seed, dict):
        seed = {{}}
    seed.setdefault("password", token(32))
    if name == "tuic":
        seed.setdefault("uuid", str(uuid.uuid4()))
    if name == "snell":
        seed.setdefault("psk", token(32))
        seed.setdefault("userkey", token(32))
    if name == "hysteria2":
        seed.setdefault("obfs_password", token(24))
    if name == "shadowtls":
        # The inner proxy credential is node runtime state, not a subscriber
        # credential. Keep it distinct from all ShadowTLS v3 user passwords.
        seed.setdefault("inner_password", token(32))
    state[name] = seed
    return seed


def tls_for(settings):
    if settings.get("tls_mode") == "custom":
        cert = str(settings.get("certificate_path") or "").strip()
        key = str(settings.get("key_path") or "").strip()
        if not cert or not key:
            raise SystemExit("custom TLS certificate paths are incomplete")
        return {{"enabled": True, "certificate_path": cert, "key_path": key}}
    return {{"enabled": True, "certificate_path": CERT, "key_path": KEY}}


def padding_lines(settings):
    if settings.get("padding_scheme") != "custom":
        return None
    raw = str(settings.get("padding_scheme_custom") or "")
    rows = [line.strip() for line in raw.splitlines() if line.strip()]
    return rows or None


def render(item):
    name = item["protocol"]
    port = int(item["port"])
    settings = dict(item.get("settings") or {{}})
    seed = seed_for(name)
    base = {{
        "type": name,
        "tag": item["tag"],
        "listen": "0.0.0.0",
        "listen_port": port,
    }}

    if name == "hysteria2":
        base["users"] = [{{"name": "twinpanel-bootstrap", "password": seed["password"]}}]
        base["tls"] = tls_for(settings)
        if bool(settings.get("ignore_client_bandwidth")):
            base["ignore_client_bandwidth"] = True
        else:
            up = int(settings.get("up_mbps") or 0)
            down = int(settings.get("down_mbps") or 0)
            if up > 0:
                base["up_mbps"] = up
            if down > 0:
                base["down_mbps"] = down
        profile = str(settings.get("bbr_profile") or "").strip()
        if profile:
            base["bbr_profile"] = profile
        obfs_type = str(settings.get("obfs_type") or "none").strip().lower()
        if obfs_type in {{"salamander", "gecko"}}:
            obfs_password = str(settings.get("obfs_password") or "").strip() or seed["obfs_password"]
            base["obfs"] = {{"type": obfs_type, "password": obfs_password}}
        masquerade = str(settings.get("masquerade") or "").strip()
        if masquerade:
            base["masquerade"] = masquerade

    elif name == "tuic":
        base["users"] = [{{
            "name": "twinpanel-bootstrap",
            "uuid": seed["uuid"],
            "password": seed["password"],
        }}]
        base["tls"] = tls_for(settings)
        base["congestion_control"] = str(settings.get("congestion_control") or "cubic")
        base["auth_timeout"] = str(settings.get("auth_timeout") or "3s")
        base["heartbeat"] = str(settings.get("heartbeat") or "10s")
        base["zero_rtt_handshake"] = bool(settings.get("zero_rtt_handshake", False))

    elif name == "anytls":
        base["users"] = [{{"name": "twinpanel-bootstrap", "password": seed["password"]}}]
        base["tls"] = tls_for(settings)
        rows = padding_lines(settings)
        if rows:
            base["padding_scheme"] = rows

    elif name == "naive":
        base["users"] = [{{"username": "twinpanel-bootstrap", "password": seed["password"]}}]
        # sing-box uses an omitted network field for TCP+UDP.
        network = str(settings.get("network") or "tcp")
        if network != "both":
            base["network"] = network
        base["quic_congestion_control"] = str(settings.get("quic_congestion_control") or "bbr")
        base["tls"] = tls_for(settings)

    elif name == "shadowtls":
        base["version"] = 3
        base["users"] = [{{"name": "twinpanel-bootstrap", "password": seed["password"]}}]
        base["handshake"] = {{
            "server": str(settings.get("handshake_server") or "www.microsoft.com"),
            "server_port": int(settings.get("handshake_port") or 443),
        }}
        base["strict_mode"] = bool(settings.get("strict_mode", True))
        wildcard = str(settings.get("wildcard_sni") or "off")
        if wildcard != "off":
            base["wildcard_sni"] = wildcard
        # ShadowTLS is a TLS camouflage transport, not the payload proxy.
        # Forward authenticated connections into the managed inner
        # Shadowsocks inbound.
        base["detour"] = SHADOWTLS_INNER_TAG

    elif name == "snell":
        version = int(settings.get("version") or 6)
        base["version"] = version
        psk = str(settings.get("psk") or "").strip() or seed["psk"]
        if version == 6 and not 12 <= len(psk.encode("utf-8")) <= 255:
            raise SystemExit("Snell v6 PSK must be 12..255 bytes")
        base["psk"] = psk
        base["users"] = [{{"name": "twinpanel-bootstrap", "userkey": seed["userkey"]}}]
        if version == 6:
            base["mode"] = str(settings.get("mode") or "default")
        else:
            base["obfs_mode"] = str(settings.get("obfs_mode") or "none")
    else:
        raise SystemExit("unsupported managed protocol: " + name)

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

for item in DESIRED:
    fresh = render(item)
    existing = by_tag.get(item["tag"])
    if isinstance(existing, dict) and existing.get("type") == fresh.get("type"):
        # Customer users are runtime state. Applying an operator preset must not
        # wipe provisioned subscriber identities.
        old_users = existing.get("users")
        if isinstance(old_users, list) and old_users:
            fresh["users"] = old_users
        existing.clear()
        existing.update(fresh)
    else:
        inbounds.append(fresh)
        by_tag[item["tag"]] = fresh

if any(item.get("protocol") == "shadowtls" for item in DESIRED):
    shadowtls_seed = seed_for("shadowtls")
    fresh_inner = {{
        "type": "shadowsocks",
        "tag": SHADOWTLS_INNER_TAG,
        "listen": "127.0.0.1",
        "method": SHADOWTLS_INNER_METHOD,
        "password": shadowtls_seed["inner_password"],
    }}
    existing_inner = by_tag.get(SHADOWTLS_INNER_TAG)
    if isinstance(existing_inner, dict) and existing_inner.get("type") == "shadowsocks":
        existing_inner.clear()
        existing_inner.update(fresh_inner)
    else:
        inbounds.append(fresh_inner)
        by_tag[SHADOWTLS_INNER_TAG] = fresh_inner

outbounds = doc.get("outbounds")
if not isinstance(outbounds, list):
    outbounds = []
if not any(isinstance(item, dict) and item.get("tag") == "direct" for item in outbounds):
    outbounds.append({{"type": "direct", "tag": "direct"}})

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
    tag = TAGS[protocol]
    tags = [tag]
    if protocol == "shadowtls":
        tags.append(SHADOWTLS_INNER_TAG)
    return f'''import json\np={CONFIG_PATH!r}\ntags={tags!r}\nwith open(p, "r", encoding="utf-8") as h:\n    doc=json.load(h)\ninbounds=doc.get("inbounds")\nif not isinstance(inbounds, list):\n    raise SystemExit("invalid sing-box config")\ndoc["inbounds"]=[x for x in inbounds if not (isinstance(x, dict) and x.get("tag") in tags)]\nwith open(p+".new", "w", encoding="utf-8") as h:\n    json.dump(doc,h,ensure_ascii=False,indent=2)\n    h.write("\\n")\nprint("remaining_inbounds="+str(len(doc["inbounds"])))\n'''


async def ensure_core(conn, node: Node) -> dict[str, str]:
    core = await _ensure_core_and_certificate(conn, node)
    version_text, version = await _read_core_version(conn)

    if version is None or version < MIN_SING_BOX_VERSION:
        # _ensure_core_and_certificate adds the official repository on clean
        # nodes. Existing nodes can already have an older binary, so make the
        # official SagerNet source explicit before refreshing package metadata.
        await cmd(
            conn,
            "set -eu; "
            "mkdir -p /etc/apt/keyrings; "
            "curl -fsSL https://sing-box.app/gpg.key -o /etc/apt/keyrings/sagernet.asc; "
            "chmod a+r /etc/apt/keyrings/sagernet.asc; "
            "printf '%s\\n' "
            "'Types: deb' "
            "'URIs: https://deb.sagernet.org/' "
            "'Suites: *' "
            "'Components: *' "
            "'Enabled: yes' "
            "'Signed-By: /etc/apt/keyrings/sagernet.asc' "
            "> /etc/apt/sources.list.d/sagernet.sources; "
            "apt-get -o DPkg::Lock::Timeout=300 update -y >/dev/null; "
            "apt-get -o DPkg::Lock::Timeout=300 install -y sing-box >/dev/null; "
            "ln -sf \"$(command -v sing-box)\" /usr/local/bin/twinpanel-sing-box",
            timeout=900,
        )
        version_text, version = await _read_core_version(conn)

    if version is None or version < MIN_SING_BOX_VERSION:
        required = ".".join(str(part) for part in MIN_SING_BOX_VERSION)
        raise ModernRuntimeV2Error(
            f"sing-box {required}+ is required; installed version: {version_text or 'unknown'}"
        )

    return {**core, "version": version_text}


async def apply_profiles(
    conn,
    node: Node,
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    if not profiles:
        raise ModernRuntimeV2Error("no protocol profiles selected")

    desired: list[dict[str, Any]] = []
    ports: set[int] = set()
    for profile in profiles:
        protocol = str(profile.get("protocol") or "").strip().lower()
        if protocol not in SINGBOX_PROTOCOLS:
            raise ModernRuntimeV2Error(f"protocol runtime is not available: {protocol}")
        port = int(profile.get("port") or PROTOCOL_CATALOG[protocol]["default_port"])
        if not 1 <= port <= 65535:
            raise ModernRuntimeV2Error(f"invalid port for {protocol}")
        if port in ports:
            raise ModernRuntimeV2Error("managed protocols cannot share a listen port")
        ports.add(port)
        desired.append({
            "protocol": protocol,
            "tag": TAGS[protocol],
            "port": port,
            "settings": dict(profile.get("settings") or {}),
        })

    core = await ensure_core(conn, node)
    script = _mutation_script(desired)
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    backup = f"{CONFIG_PATH}.bak-v2-$(date +%Y%m%d-%H%M%S)"
    await cmd(
        conn,
        "set -eu; "
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3; "
        f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.new')}; "
        f"if [ -s {shlex.quote(CONFIG_PATH)} ]; then cp -a {shlex.quote(CONFIG_PATH)} {backup}; fi; "
        f"mv {shlex.quote(CONFIG_PATH + '.new')} {shlex.quote(CONFIG_PATH)}; "
        f"chmod 600 {shlex.quote(CONFIG_PATH)}; "
        f"if ! systemctl restart {SERVICE_NAME}.service; then "
        f"  last=$(ls -1t {shlex.quote(CONFIG_PATH)}.bak-v2-* 2>/dev/null | head -n1 || true); "
        f"  if [ -n \"$last\" ]; then cp -a \"$last\" {shlex.quote(CONFIG_PATH)}; systemctl restart {SERVICE_NAME}.service || true; fi; "
        "  exit 72; "
        "fi; "
        f"systemctl is-active --quiet {SERVICE_NAME}.service",
        timeout=180,
    )

    results: dict[str, Any] = {}
    for item in desired:
        protocol = item["protocol"]
        port = int(item["port"])
        await ufw_allow(conn, port, _transport(protocol))
        results[protocol] = await profile_health(conn, protocol, port)
    return {"core": core, "protocols": results}


async def profile_health(conn, protocol: str, port: int | None = None) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_PROTOCOLS:
        raise ModernRuntimeV2Error(f"protocol runtime is not available: {protocol}")
    listen_port = int(port or PROTOCOL_CATALOG[protocol]["default_port"])
    transport = _transport(protocol)
    service_ok = await active(conn, SERVICE_NAME)
    listen_ok = await listener(conn, listen_port, transport)
    return {
        "ok": bool(service_ok and listen_ok),
        "protocol": protocol,
        "name": PROTOCOL_CATALOG[protocol]["title"],
        "service": SERVICE_NAME,
        "service_active": bool(service_ok),
        "listener": bool(listen_ok),
        "port": listen_port,
        "transport": transport,
    }


async def remove_profile(conn, protocol: str) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_PROTOCOLS:
        raise ModernRuntimeV2Error(f"protocol runtime is not available: {protocol}")
    exists = (await cmd(
        conn,
        f"test -s {shlex.quote(CONFIG_PATH)} && echo yes || true",
        check=False,
    )).strip()
    if exists != "yes":
        return {"ok": True, "protocol": protocol, "removed": False, "remaining": 0}

    encoded = base64.b64encode(_remove_script(protocol).encode()).decode()
    output = await cmd(
        conn,
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3",
        timeout=60,
    )
    match = re.search(r"remaining_inbounds=(\d+)", output)
    remaining = int(match.group(1)) if match else 0
    backup_pattern = f"{shlex.quote(CONFIG_PATH)}.bak-remove-*"
    backup_target = f"{shlex.quote(CONFIG_PATH)}.bak-remove-$(date +%Y%m%d-%H%M%S)"

    if remaining:
        await cmd(
            conn,
            "set -eu; "
            f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.new')}; "
            f"cp -a {shlex.quote(CONFIG_PATH)} {backup_target}; "
            f"mv {shlex.quote(CONFIG_PATH + '.new')} {shlex.quote(CONFIG_PATH)}; "
            f"if ! systemctl restart {SERVICE_NAME}.service; then "
            f"  last=$(ls -1t {backup_pattern} 2>/dev/null | head -n1 || true); "
            f"  if [ -n \"$last\" ]; then cp -a \"$last\" {shlex.quote(CONFIG_PATH)}; systemctl restart {SERVICE_NAME}.service || true; fi; "
            "  exit 73; "
            "fi",
            timeout=120,
        )
    else:
        await cmd(
            conn,
            "set -eu; "
            f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.new')}; "
            f"cp -a {shlex.quote(CONFIG_PATH)} {backup_target}; "
            f"mv {shlex.quote(CONFIG_PATH + '.new')} {shlex.quote(CONFIG_PATH)}; "
            f"systemctl disable --now {SERVICE_NAME}.service >/dev/null 2>&1 || true",
            timeout=120,
        )

    return {"ok": True, "protocol": protocol, "removed": True, "remaining": remaining}


def redacted_preview(protocol: str, port: int, settings: dict[str, Any]) -> dict[str, Any]:
    definition = PROTOCOL_CATALOG[protocol]
    result = {
        "type": protocol,
        "tag": TAGS.get(protocol, f"twinpanel-{protocol}-in"),
        "listen": "0.0.0.0",
        "listen_port": int(port),
        "settings": dict(settings),
        "core": definition.get("core"),
        "adapter": definition.get("adapter"),
    }
    for field in definition.get("fields", []):
        if field.get("secret") and field.get("key") in result["settings"]:
            if result["settings"][field["key"]]:
                result["settings"][field["key"]] = "••••••••"
    return result