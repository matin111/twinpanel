from __future__ import annotations

import base64
import ipaddress
import json
import re
import shlex
from typing import Any

from .models import Node
from .protocol_catalog import PROTOCOL_CATALOG
from .routers.provision import active, cmd, ufw_allow


STANDALONE_PROTOCOLS = {"mieru", "trusttunnel", "amneziawg", "sudoku"}

MIERU_VERSION = "3.38.1"
TRUSTTUNNEL_VERSION = "1.1.0"
SUDOKU_VERSION = "0.5.1"

BASE_DIR = "/etc/twinpanel/standalone"

RUNTIME_OVERRIDES: dict[str, dict[str, Any]] = {
    "mieru": {"runtime_status": "ready"},
    "trusttunnel": {"runtime_status": "ready"},
    "amneziawg": {"runtime_status": "ready"},
    "sudoku": {
        "runtime_status": "ready",
        "transport": "tcp",
        "platforms": ["android", "ios", "windows", "macos", "linux"],
    },
}


class StandaloneProtocolError(RuntimeError):
    pass


def activate_catalog() -> None:
    for key, values in RUNTIME_OVERRIDES.items():
        if key in PROTOCOL_CATALOG:
            PROTOCOL_CATALOG[key].update(values)


activate_catalog()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


async def _write(conn, path: str, text: str, mode: str = "600") -> None:
    encoded = _b64(text)
    await cmd(
        conn,
        "set -eu; "
        f"install -d -m 700 {shlex.quote(path.rsplit('/', 1)[0])}; "
        f"printf '%s' {shlex.quote(encoded)} | base64 -d > {shlex.quote(path)}.new; "
        f"chmod {mode} {shlex.quote(path)}.new; "
        f"mv {shlex.quote(path)}.new {shlex.quote(path)}",
        timeout=60,
    )


async def _tcp_listener(conn, port: int) -> bool:
    value = (
        await cmd(
            conn,
            f"ss -H -lnt | awk '$4 ~ /:{int(port)}$/ {{found=1}} END {{if (found) print \"yes\"}}'",
            check=False,
        )
    ).strip()
    return value == "yes"


async def _udp_listener(conn, port: int) -> bool:
    value = (
        await cmd(
            conn,
            f"ss -H -lnu | awk '$5 ~ /:{int(port)}$/ || $4 ~ /:{int(port)}$/ {{found=1}} END {{if (found) print \"yes\"}}'",
            check=False,
        )
    ).strip()
    return value == "yes"


def _node_identity(node: Node) -> tuple[str, str]:
    domain = str(getattr(node, "public_domain", None) or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/", 1)[0].split(":", 1)[0]
    ip = str(getattr(node, "public_ip", None) or "").strip()
    return domain, ip


def _is_dns_hostname(value: str) -> bool:
    hostname = str(value or "").strip().lower().rstrip(".")
    if not hostname or len(hostname) > 253:
        return False
    try:
        ipaddress.ip_address(hostname)
        return False
    except ValueError:
        pass
    labels = hostname.split(".")
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) is not None
        for label in labels
    )


def _trusttunnel_tls_hostname(node: Node) -> str:
    """Return a DNS-shaped TLS identity independent from the transport address.

    TrustTunnel's official client omits SNI when endpoint.hostname is an IP.
    The endpoint then drops the TLS connection before the handshake completes.
    Use a configured public DNS name when available; otherwise use a stable,
    reserved .invalid identity. Client delivery still carries the Exit IP in
    endpoint.addresses, so the synthetic identity never needs DNS resolution.
    """

    domain, ip = _node_identity(node)
    if _is_dns_hostname(domain):
        return domain.rstrip(".")

    node_id = int(getattr(node, "id", 0) or 0)
    if node_id > 0:
        return f"tt-node-{node_id}.twinpanel.invalid"

    address = ip or domain
    if address:
        token = re.sub(r"[^a-z0-9]+", "-", address.lower()).strip("-")[:48]
        if token:
            return f"tt-{token}.twinpanel.invalid"

    raise StandaloneProtocolError("TrustTunnel requires a public domain or IP")


async def _ensure_bootstrap_secret(conn, protocol: str) -> dict[str, str]:
    path = f"{BASE_DIR}/{protocol}/bootstrap.json"
    script = f'''import json, os, secrets
path={path!r}
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
    with open(path, "r", encoding="utf-8") as h:
        state=json.load(h)
except Exception:
    state={{}}
if not isinstance(state, dict):
    state={{}}
state.setdefault("username", "twinpanel-bootstrap")
state.setdefault("password", secrets.token_urlsafe(32))
with open(path+".new", "w", encoding="utf-8") as h:
    json.dump(state, h, separators=(",", ":"))
    h.write("\\n")
os.chmod(path+".new", 0o600)
os.replace(path+".new", path)
print(json.dumps(state, separators=(",", ":")))
'''
    raw = await cmd(
        conn,
        f"printf '%s' {shlex.quote(_b64(script))} | base64 -d | python3",
        timeout=60,
    )
    try:
        value = json.loads(raw.strip().splitlines()[-1])
    except Exception as exc:
        raise StandaloneProtocolError(f"failed to create {protocol} bootstrap credentials") from exc
    return {"username": str(value["username"]), "password": str(value["password"])}


async def _install_mieru_binary(conn) -> dict[str, str]:
    script = f'''set -eu
export DEBIAN_FRONTEND=noninteractive
arch="$(dpkg --print-architecture)"
case "$arch" in
  amd64)
    url="https://github.com/enfein/mieru/releases/download/v{MIERU_VERSION}/mita_{MIERU_VERSION}_amd64.deb"
    sha="2c7c0be33d34cf126187d97c17484a34b5c62b764c96b0a88ec4cbc7660d72c9"
    ;;
  arm64)
    url="https://github.com/enfein/mieru/releases/download/v{MIERU_VERSION}/mita_{MIERU_VERSION}_arm64.deb"
    sha="3def1c31b8a060c5842649857dc5a500fa0027503fa66440a49005038c94934c"
    ;;
  *)
    echo "unsupported architecture for Mieru: $arch" >&2
    exit 64
    ;;
esac
if ! command -v mita >/dev/null 2>&1 || ! mita version 2>&1 | grep -q {shlex.quote(MIERU_VERSION)}; then
  apt-get -o DPkg::Lock::Timeout=300 update -y >/dev/null
  apt-get -o DPkg::Lock::Timeout=300 install -y ca-certificates curl >/dev/null
  tmp="$(mktemp --suffix=.deb)"
  trap 'rm -f "$tmp"' EXIT
  curl -fL --retry 3 --connect-timeout 20 "$url" -o "$tmp"
  echo "$sha  $tmp" | sha256sum -c -
  dpkg -i "$tmp" >/dev/null || apt-get -o DPkg::Lock::Timeout=300 -f install -y >/dev/null
fi
command -v mita
mita version 2>&1 | head -n1
'''
    output = await cmd(conn, script, timeout=900)
    return {"version": output.strip().splitlines()[-1] if output.strip() else MIERU_VERSION}


async def _apply_mieru(conn, node: Node, port: int, settings: dict[str, Any]) -> dict[str, Any]:
    core = await _install_mieru_binary(conn)
    secret = await _ensure_bootstrap_secret(conn, "mieru")
    config_path = f"{BASE_DIR}/mieru/server.json"
    config = {
        "portBindings": [
            {"port": int(port), "protocol": "TCP"},
            {"port": int(port), "protocol": "UDP"},
        ],
        "users": [{"name": secret["username"], "password": secret["password"]}],
        "loggingLevel": "INFO",
        "mtu": int(settings.get("mtu") or 1400),
        "dns": {"dualStack": str(settings.get("dual_stack") or "PREFER_IPv4")},
    }
    await _write(conn, config_path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    rollback = f"{BASE_DIR}/mieru/previous.json"
    await cmd(
        conn,
        "set -eu; "
        f"install -d -m 700 {shlex.quote(BASE_DIR + '/mieru')}; "
        f"mita describe config > {shlex.quote(rollback)} 2>/dev/null || true; "
        "mita stop >/dev/null 2>&1 || true; "
        f"if ! mita replace config {shlex.quote(config_path)} >/dev/null 2>&1 || ! mita start >/dev/null 2>&1; then "
        f"  if [ -s {shlex.quote(rollback)} ]; then mita replace config {shlex.quote(rollback)} >/dev/null 2>&1 || true; mita start >/dev/null 2>&1 || true; fi; "
        "  exit 72; "
        "fi",
        timeout=120,
    )
    await ufw_allow(conn, int(port), "tcp")
    await ufw_allow(conn, int(port), "udp")
    result = await standalone_health(conn, "mieru", int(port))
    result["core"] = core
    return result


async def _ensure_trusttunnel_binary(conn) -> dict[str, str]:
    script = f'''set -eu
arch="$(uname -m)"
case "$arch" in
  x86_64|amd64)
    asset="trusttunnel-v{TRUSTTUNNEL_VERSION}-linux-x86_64.tar.gz"
    sha="91c2ea3db7416a01b5258a4c047ec22890490bc55e1b194206031aa75144f0e7"
    ;;
  aarch64|arm64)
    asset="trusttunnel-v{TRUSTTUNNEL_VERSION}-linux-aarch64.tar.gz"
    sha="c2aee17a1ced349283cba4775202e2baba053b8ea835d4cc23dc67d16c6b9686"
    ;;
  *)
    echo "unsupported architecture for TrustTunnel: $arch" >&2
    exit 64
    ;;
esac
install -d -m 755 /opt/twinpanel/trusttunnel
if [ ! -x /opt/twinpanel/trusttunnel/trusttunnel_endpoint ] || ! /opt/twinpanel/trusttunnel/trusttunnel_endpoint --version 2>&1 | grep -q {shlex.quote(TRUSTTUNNEL_VERSION)}; then
  apt-get -o DPkg::Lock::Timeout=300 update -y >/dev/null
  apt-get -o DPkg::Lock::Timeout=300 install -y ca-certificates curl tar openssl >/dev/null
  tmp="$(mktemp --suffix=.tar.gz)"
  dir="$(mktemp -d)"
  trap 'rm -f "$tmp"; rm -rf "$dir"' EXIT
  curl -fL --retry 3 --connect-timeout 20 "https://github.com/TrustTunnel/TrustTunnel/releases/download/v{TRUSTTUNNEL_VERSION}/$asset" -o "$tmp"
  echo "$sha  $tmp" | sha256sum -c -
  tar -xzf "$tmp" -C "$dir"
  bin="$(find "$dir" -type f -name trusttunnel_endpoint -perm -u+x | head -n1)"
  [ -n "$bin" ]
  install -m 755 "$bin" /opt/twinpanel/trusttunnel/trusttunnel_endpoint
fi
/opt/twinpanel/trusttunnel/trusttunnel_endpoint --version 2>&1 | head -n1
'''
    output = await cmd(conn, script, timeout=900)
    return {"version": output.strip().splitlines()[-1] if output.strip() else TRUSTTUNNEL_VERSION}


async def _ensure_trusttunnel_cert(conn, node: Node) -> tuple[str, str, str]:
    directory = f"{BASE_DIR}/trusttunnel"
    cert = f"{directory}/server.crt"
    key = f"{directory}/server.key"
    domain, ip = _node_identity(node)
    if not domain and not ip:
        raise StandaloneProtocolError("TrustTunnel requires a public domain or IP")

    name = _trusttunnel_tls_hostname(node)
    sans = [f"DNS:{name}"]
    if ip:
        sans.append(f"IP:{ip}")
    elif domain:
        try:
            ipaddress.ip_address(domain)
        except ValueError:
            pass
        else:
            sans.append(f"IP:{domain}")
    san = ",".join(sans)
    required_dns_san = f"DNS:{name}"

    await cmd(
        conn,
        "set -eu; "
        f"install -d -m 700 {shlex.quote(directory)}; "
        "command -v openssl >/dev/null 2>&1 || "
        "apt-get -o DPkg::Lock::Timeout=300 install -y openssl >/dev/null; "
        f"if [ ! -s {shlex.quote(cert)} ] || [ ! -s {shlex.quote(key)} ] || "
        f"! openssl x509 -in {shlex.quote(cert)} -noout -ext subjectAltName 2>/dev/null "
        "| tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' "
        f"| grep -Fqx {shlex.quote(required_dns_san)}; then "
        f"rm -f {shlex.quote(cert + '.new')} {shlex.quote(key + '.new')}; "
        "openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -sha256 -nodes -days 3650 "
        f"-subj {shlex.quote('/CN=' + name)} -addext {shlex.quote('subjectAltName=' + san)} "
        f"-keyout {shlex.quote(key + '.new')} -out {shlex.quote(cert + '.new')} >/dev/null 2>&1; "
        f"chmod 600 {shlex.quote(key + '.new')}; chmod 644 {shlex.quote(cert + '.new')}; "
        f"mv {shlex.quote(key + '.new')} {shlex.quote(key)}; "
        f"mv {shlex.quote(cert + '.new')} {shlex.quote(cert)}; "
        "fi; "
        f"chmod 600 {shlex.quote(key)}; chmod 644 {shlex.quote(cert)}",
        timeout=120,
    )
    return name, cert, key


async def _apply_trusttunnel(conn, node: Node, port: int, settings: dict[str, Any]) -> dict[str, Any]:
    core = await _ensure_trusttunnel_binary(conn)
    secret = await _ensure_bootstrap_secret(conn, "trusttunnel")
    hostname, cert, key = await _ensure_trusttunnel_cert(conn, node)
    directory = f"{BASE_DIR}/trusttunnel"
    credentials = f'''[[client]]
username = {json.dumps(secret["username"])}
password = {json.dumps(secret["password"])}
max_http2_conns = {int(settings.get("connection_limit") or 4)}
max_http3_conns = {int(settings.get("connection_limit") or 4)}
'''
    sections: list[str] = []
    if bool(settings.get("http1", True)):
        sections.append("[listen_protocols.http1]\nupload_buffer_size = 32768")
    if bool(settings.get("http2", True)):
        sections.append("[listen_protocols.http2]\nmax_concurrent_streams = 1000")
    if bool(settings.get("quic", True)):
        sections.append("[listen_protocols.quic]\nenable_early_data = false")
    if not sections:
        raise StandaloneProtocolError("TrustTunnel requires at least one listen protocol")
    vpn = f'''listen_address = "0.0.0.0:{int(port)}"
ipv6_available = true
allow_private_network_connections = false
credentials_file = {json.dumps(directory + "/credentials.toml")}
default_max_http2_conns_per_client = {int(settings.get("connection_limit") or 4)}
default_max_http3_conns_per_client = {int(settings.get("connection_limit") or 4)}

{chr(10).join(sections)}

[forward_protocol]
direct = {{}}
'''
    if bool(settings.get("per_client_metrics", True)):
        vpn += '\n[metrics]\naddress = "127.0.0.1:1987"\nrequest_timeout_secs = 3\nper_client_metrics = true\n'
    hosts = f'''[[main_hosts]]
hostname = {json.dumps(hostname)}
cert_chain_path = {json.dumps(cert)}
private_key_path = {json.dumps(key)}
'''
    await _write(conn, f"{directory}/credentials.toml", credentials)
    await _write(conn, f"{directory}/vpn.toml", vpn)
    await _write(conn, f"{directory}/hosts.toml", hosts)
    service = f'''[Unit]
Description=TwinPanel TrustTunnel endpoint
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/twinpanel/trusttunnel
ExecStart=/opt/twinpanel/trusttunnel/trusttunnel_endpoint {directory}/vpn.toml {directory}/hosts.toml
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
'''
    await _write(conn, "/etc/systemd/system/twinpanel-trusttunnel.service", service, mode="644")
    await cmd(
        conn,
        "systemctl daemon-reload && "
        "systemctl enable twinpanel-trusttunnel.service >/dev/null && "
        "systemctl restart twinpanel-trusttunnel.service",
        timeout=120,
    )
    await ufw_allow(conn, int(port), "tcp")
    if bool(settings.get("quic", True)):
        await ufw_allow(conn, int(port), "udp")
    result = await standalone_health(conn, "trusttunnel", int(port))
    result["core"] = core
    result["tls_hostname"] = hostname
    return result


async def _ensure_amneziawg(conn) -> dict[str, str]:
    script = r'''set -eu
export DEBIAN_FRONTEND=noninteractive
if ! command -v awg >/dev/null 2>&1 || ! command -v awg-quick >/dev/null 2>&1; then
  apt-get -o DPkg::Lock::Timeout=300 update -y >/dev/null
  apt-get -o DPkg::Lock::Timeout=300 install -y software-properties-common python3-launchpadlib gnupg2 ca-certificates "linux-headers-$(uname -r)" >/dev/null
  . /etc/os-release
  if [ "${ID:-}" = "ubuntu" ]; then
    add-apt-repository -y ppa:amnezia/ppa >/dev/null
  else
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 57290828 >/dev/null 2>&1
    printf '%s\n' \
      'deb https://ppa.launchpadcontent.net/amnezia/ppa/ubuntu focal main' \
      'deb-src https://ppa.launchpadcontent.net/amnezia/ppa/ubuntu focal main' \
      > /etc/apt/sources.list.d/amneziawg.list
  fi
  apt-get -o DPkg::Lock::Timeout=300 update -y >/dev/null
  apt-get -o DPkg::Lock::Timeout=300 install -y amneziawg >/dev/null
fi
modprobe amneziawg
command -v awg
command -v awg-quick
'''
    output = await cmd(conn, script, timeout=1200)
    return {"binary": output.strip().splitlines()[-2] if len(output.strip().splitlines()) >= 2 else "awg"}


async def _awg_private_key(conn) -> str:
    path = f"{BASE_DIR}/amneziawg/private.key"
    output = await cmd(
        conn,
        "set -eu; "
        f"install -d -m 700 {shlex.quote(BASE_DIR + '/amneziawg')}; "
        f"if [ ! -s {shlex.quote(path)} ]; then umask 077; awg genkey > {shlex.quote(path)}; fi; "
        f"chmod 600 {shlex.quote(path)}; cat {shlex.quote(path)}",
        timeout=60,
    )
    key = output.strip().splitlines()[-1] if output.strip() else ""
    if not key:
        raise StandaloneProtocolError("AmneziaWG private key generation failed")
    return key


async def _apply_amneziawg(conn, node: Node, port: int, settings: dict[str, Any]) -> dict[str, Any]:
    core = await _ensure_amneziawg(conn)
    private_key = await _awg_private_key(conn)
    interface = "tpawg0"
    config = f'''[Interface]
Address = 10.254.252.1/24
ListenPort = {int(port)}
PrivateKey = {private_key}
MTU = {int(settings.get("mtu") or 1280)}
Jc = {int(settings.get("jc") or 6)}
Jmin = {int(settings.get("jmin") or 8)}
Jmax = {int(settings.get("jmax") or 80)}
S1 = {int(settings.get("s1") or 64)}
S2 = {int(settings.get("s2") or 96)}
H1 = {int(settings.get("h1") or 101)}
H2 = {int(settings.get("h2") or 202)}
H3 = {int(settings.get("h3") or 303)}
H4 = {int(settings.get("h4") or 404)}
'''
    config_path = f"/etc/amnezia/amneziawg/{interface}.conf"
    await _write(conn, config_path, config)
    service = f'''[Unit]
Description=TwinPanel AmneziaWG interface
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/awg-quick up {config_path}
ExecStop=/usr/bin/awg-quick down {config_path}

[Install]
WantedBy=multi-user.target
'''
    await _write(conn, "/etc/systemd/system/twinpanel-amneziawg.service", service, mode="644")
    await cmd(
        conn,
        "set -eu; "
        f"awg-quick down {shlex.quote(config_path)} >/dev/null 2>&1 || true; "
        "systemctl daemon-reload; "
        "systemctl enable twinpanel-amneziawg.service >/dev/null; "
        "systemctl restart twinpanel-amneziawg.service",
        timeout=180,
    )
    await ufw_allow(conn, int(port), "udp")
    result = await standalone_health(conn, "amneziawg", int(port))
    result["core"] = core
    return result


async def _ensure_sudoku_binary(conn) -> dict[str, str]:
    script = f'''set -eu
arch="$(uname -m)"
case "$arch" in
  x86_64|amd64)
    asset="sudoku-linux-amd64.tar.gz"
    sha="a9ebfb7e359d7f667062400a098e117e4e2bed55c65aea099e949129953028d0"
    ;;
  aarch64|arm64)
    asset="sudoku-linux-arm64.tar.gz"
    sha="2c8f66382fec8ff81980364022127ac36d6a34d558e9f20c5204df0bc03a044f"
    ;;
  *)
    echo "unsupported architecture for Sudoku: $arch" >&2
    exit 64
    ;;
esac
if [ ! -x /usr/local/bin/twinpanel-sudoku ]; then
  apt-get -o DPkg::Lock::Timeout=300 update -y >/dev/null
  apt-get -o DPkg::Lock::Timeout=300 install -y ca-certificates curl tar >/dev/null
  tmp="$(mktemp --suffix=.tar.gz)"
  dir="$(mktemp -d)"
  trap 'rm -f "$tmp"; rm -rf "$dir"' EXIT
  curl -fL --retry 3 --connect-timeout 20 "https://github.com/SUDOKU-ASCII/sudoku/releases/download/v{SUDOKU_VERSION}/$asset" -o "$tmp"
  echo "$sha  $tmp" | sha256sum -c -
  tar -xzf "$tmp" -C "$dir"
  bin="$(find "$dir" -type f \\( -name sudoku -o -name sudoku-tunnel \\) -perm -u+x | head -n1)"
  [ -n "$bin" ]
  install -m 755 "$bin" /usr/local/bin/twinpanel-sudoku
fi
/usr/local/bin/twinpanel-sudoku -h 2>&1 | head -n1 || true
'''
    output = await cmd(conn, script, timeout=900)
    return {"version": SUDOKU_VERSION, "banner": output.strip().splitlines()[-1] if output.strip() else ""}


async def _sudoku_keys(conn) -> dict[str, str]:
    state = f"{BASE_DIR}/sudoku/keys.json"
    script = f'''import json, os, re, subprocess
path={state!r}
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
    with open(path, "r", encoding="utf-8") as h:
        value=json.load(h)
except Exception:
    value={{}}
if not isinstance(value, dict) or not value.get("master_public_key") or not value.get("available_private_key"):
    out=subprocess.check_output(["/usr/local/bin/twinpanel-sudoku", "-keygen"], text=True, stderr=subprocess.STDOUT)
    def pick(name):
        m=re.search(re.escape(name)+r":\\s*([0-9a-fA-F]+)\\s*$", out, re.M)
        if not m:
            raise SystemExit("missing "+name)
        return m.group(1)
    value={{
        "available_private_key": pick("Available Private Key"),
        "master_private_key": pick("Master Private Key"),
        "master_public_key": pick("Master Public Key"),
    }}
    with open(path+".new", "w", encoding="utf-8") as h:
        json.dump(value, h, separators=(",", ":"))
        h.write("\\n")
    os.chmod(path+".new", 0o600)
    os.replace(path+".new", path)
print(json.dumps(value, separators=(",", ":")))
'''
    raw = await cmd(
        conn,
        f"printf '%s' {shlex.quote(_b64(script))} | base64 -d | python3",
        timeout=60,
    )
    try:
        value = json.loads(raw.strip().splitlines()[-1])
    except Exception as exc:
        raise StandaloneProtocolError("Sudoku key generation failed") from exc
    return {str(k): str(v) for k, v in value.items()}


async def _apply_sudoku(conn, node: Node, port: int, settings: dict[str, Any]) -> dict[str, Any]:
    core = await _ensure_sudoku_binary(conn)
    keys = await _sudoku_keys(conn)
    config_path = f"{BASE_DIR}/sudoku/server.config.json"
    config = {
        "mode": "server",
        "transport": "tcp",
        "local_port": int(port),
        "fallback_address": "127.0.0.1:80",
        "key": keys["master_public_key"],
        "aead": "chacha20-poly1305",
        "suspicious_action": "fallback",
        "padding_min": 5,
        "padding_max": 15,
        "custom_table": "",
        "custom_tables": [],
        "ascii": "prefer_entropy",
        "enable_pure_downlink": True,
        "multiplex": "off",
        "httpmask": {"disable": False, "mode": "auto", "tls": False, "host": "", "path_root": ""},
        "reverse": {"listen": ""},
    }
    await _write(conn, config_path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    service = f'''[Unit]
Description=TwinPanel Sudoku proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/twinpanel-sudoku -c {config_path}
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
'''
    await _write(conn, "/etc/systemd/system/twinpanel-sudoku.service", service, mode="644")
    await cmd(
        conn,
        "systemctl daemon-reload && "
        "systemctl enable twinpanel-sudoku.service >/dev/null && "
        "systemctl restart twinpanel-sudoku.service",
        timeout=120,
    )
    await ufw_allow(conn, int(port), "tcp")
    result = await standalone_health(conn, "sudoku", int(port))
    result["core"] = core
    result["client_bootstrap_key_available"] = bool(keys.get("available_private_key"))
    return result


async def apply_standalone_profile(
    conn,
    node: Node,
    profile: dict[str, Any],
) -> dict[str, Any]:
    protocol = str(profile.get("protocol") or "").strip().lower()
    if protocol not in STANDALONE_PROTOCOLS:
        raise StandaloneProtocolError(f"unsupported standalone protocol: {protocol}")
    port = int(profile.get("port") or PROTOCOL_CATALOG[protocol]["default_port"])
    settings = dict(profile.get("settings") or {})
    if protocol == "mieru":
        return await _apply_mieru(conn, node, port, settings)
    if protocol == "trusttunnel":
        return await _apply_trusttunnel(conn, node, port, settings)
    if protocol == "amneziawg":
        return await _apply_amneziawg(conn, node, port, settings)
    return await _apply_sudoku(conn, node, port, settings)


async def standalone_health(conn, protocol: str, port: int | None = None) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in STANDALONE_PROTOCOLS:
        raise StandaloneProtocolError(f"unsupported standalone protocol: {protocol}")
    listen_port = int(port or PROTOCOL_CATALOG[protocol]["default_port"])
    if protocol == "mieru":
        service_ok = await active(conn, "mita")
        status = (await cmd(conn, "mita status 2>&1 || true", check=False)).upper()
        tcp_ok = await _tcp_listener(conn, listen_port)
        udp_ok = await _udp_listener(conn, listen_port)
        ok = bool(service_ok and "RUNNING" in status and tcp_ok and udp_ok)
        return {
            "ok": ok,
            "protocol": protocol,
            "service": "mita",
            "service_active": bool(service_ok),
            "listener": bool(tcp_ok and udp_ok),
            "tcp_listener": tcp_ok,
            "udp_listener": udp_ok,
            "port": listen_port,
            "transport": "tcp_udp",
        }
    if protocol == "trusttunnel":
        service_ok = await active(conn, "twinpanel-trusttunnel")
        tcp_ok = await _tcp_listener(conn, listen_port)
        udp_ok = await _udp_listener(conn, listen_port)
        return {
            "ok": bool(service_ok and (tcp_ok or udp_ok)),
            "protocol": protocol,
            "service": "twinpanel-trusttunnel",
            "service_active": bool(service_ok),
            "listener": bool(tcp_ok or udp_ok),
            "tcp_listener": tcp_ok,
            "udp_listener": udp_ok,
            "port": listen_port,
            "transport": "tcp_udp_quic",
        }
    if protocol == "amneziawg":
        service_ok = await active(conn, "twinpanel-amneziawg")
        iface = (
            await cmd(conn, "awg show tpawg0 >/dev/null 2>&1 && echo yes || true", check=False)
        ).strip() == "yes"
        udp_ok = await _udp_listener(conn, listen_port)
        return {
            "ok": bool(service_ok and iface and udp_ok),
            "protocol": protocol,
            "service": "twinpanel-amneziawg",
            "service_active": bool(service_ok),
            "listener": udp_ok,
            "interface": iface,
            "port": listen_port,
            "transport": "udp",
        }
    service_ok = await active(conn, "twinpanel-sudoku")
    tcp_ok = await _tcp_listener(conn, listen_port)
    return {
        "ok": bool(service_ok and tcp_ok),
        "protocol": protocol,
        "service": "twinpanel-sudoku",
        "service_active": bool(service_ok),
        "listener": tcp_ok,
        "port": listen_port,
        "transport": "tcp",
    }


async def remove_standalone(conn, protocol: str) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in STANDALONE_PROTOCOLS:
        raise StandaloneProtocolError(f"unsupported standalone protocol: {protocol}")
    service = {
        "mieru": "mita",
        "trusttunnel": "twinpanel-trusttunnel",
        "amneziawg": "twinpanel-amneziawg",
        "sudoku": "twinpanel-sudoku",
    }[protocol]
    if protocol == "mieru":
        await cmd(conn, "mita stop >/dev/null 2>&1 || true", check=False)
    else:
        await cmd(
            conn,
            f"systemctl disable --now {shlex.quote(service)}.service >/dev/null 2>&1 || true",
            check=False,
        )
    return {"ok": True, "protocol": protocol, "removed": True, "remaining": 0}


def standalone_preview(protocol: str, port: int, settings: dict[str, Any]) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in STANDALONE_PROTOCOLS:
        raise StandaloneProtocolError(f"unsupported standalone protocol: {protocol}")
    return {
        "type": protocol,
        "listen": "0.0.0.0",
        "listen_port": int(port),
        "core": PROTOCOL_CATALOG[protocol]["core"],
        "adapter": PROTOCOL_CATALOG[protocol]["adapter"],
        "settings": dict(settings),
    }
