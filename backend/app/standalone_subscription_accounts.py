from __future__ import annotations

import base64
import json
import re
import secrets
import shlex
from dataclasses import asdict, dataclass
from typing import Any

from .models import Node
from .routers.provision import cmd, ufw_allow


STANDALONE_ACCOUNT_PROTOCOLS = frozenset({
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
})
BASE_DIR = "/etc/twinpanel/standalone"
ACCOUNT_DIR = f"{BASE_DIR}/accounts"
REVOCATION_SENTINEL = "__twinpanel_revoked__"


class StandaloneAccountError(RuntimeError):
    pass


@dataclass(frozen=True)
class StandaloneAccountSecret:
    protocol: str
    subscription_id: int
    username: str
    password: str | None = None
    client_private_key: str | None = None
    client_public_key: str | None = None
    address: str | None = None
    server_public_key: str | None = None
    sudoku_master_private_key: str | None = None
    sudoku_master_public_key: str | None = None
    sudoku_client_key: str | None = None
    sudoku_port: int | None = None


def account_username(subscription_id: int) -> str:
    value = int(subscription_id)
    if value <= 0:
        raise ValueError("subscription_id must be positive")
    return f"tp-sub-{value}"


def secret_to_dict(secret: StandaloneAccountSecret) -> dict[str, Any]:
    return asdict(secret)


def secret_from_dict(value: dict[str, Any]) -> StandaloneAccountSecret:
    protocol = str(value.get("protocol") or "").strip().lower()
    if protocol not in STANDALONE_ACCOUNT_PROTOCOLS:
        raise StandaloneAccountError(f"unsupported standalone account protocol: {protocol}")
    return StandaloneAccountSecret(
        protocol=protocol,
        subscription_id=int(value.get("subscription_id") or 0),
        username=str(value.get("username") or "").strip(),
        password=str(value["password"]) if value.get("password") else None,
        client_private_key=str(value["client_private_key"]) if value.get("client_private_key") else None,
        client_public_key=str(value["client_public_key"]) if value.get("client_public_key") else None,
        address=str(value["address"]) if value.get("address") else None,
        server_public_key=str(value["server_public_key"]) if value.get("server_public_key") else None,
        sudoku_master_private_key=str(value["sudoku_master_private_key"]) if value.get("sudoku_master_private_key") else None,
        sudoku_master_public_key=str(value["sudoku_master_public_key"]) if value.get("sudoku_master_public_key") else None,
        sudoku_client_key=str(value["sudoku_client_key"]) if value.get("sudoku_client_key") else None,
        sudoku_port=int(value["sudoku_port"]) if value.get("sudoku_port") else None,
    )


def _node_host(node: Node) -> str:
    return str(
        getattr(node, "public_domain", None)
        or getattr(node, "public_ip", None)
        or ""
    ).strip()


def _encode_script(script: str) -> str:
    return base64.b64encode(script.encode("utf-8")).decode("ascii")


async def _run_python(conn, script: str, *, timeout: int = 90) -> str:
    encoded = _encode_script(script)
    return await cmd(
        conn,
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3",
        timeout=timeout,
    )


def _awg_address(subscription_id: int) -> str:
    # 10.254/16 is reserved for the standalone AmneziaWG account pool.
    # Keep .0.0 and .0.1 for network/server and map subscriptions over the
    # remaining 65533 addresses. Collision after a full pool wrap is rejected
    # by the runtime state instead of silently sharing an address.
    slot = ((int(subscription_id) - 1) % 65533) + 2
    return f"10.254.{slot // 256}.{slot % 256}/32"


def _sudoku_port(subscription_id: int) -> int:
    # Per-user Sudoku instances are required for independent revoke because a
    # server master public key accepts all derived private keys. A dedicated
    # listener gives every subscription an independently stoppable identity.
    return 30000 + ((int(subscription_id) - 1) % 30000)


async def _new_awg_secret(conn, subscription_id: int) -> StandaloneAccountSecret:
    raw = await cmd(
        conn,
        "set -eu; priv=$(awg genkey); pub=$(printf '%s\\n' \"$priv\" | awg pubkey); "
        "python3 -c 'import json,sys; print(json.dumps({\"private\":sys.argv[1],\"public\":sys.argv[2]}))' \"$priv\" \"$pub\"",
        timeout=60,
    )
    try:
        pair = json.loads(raw.strip().splitlines()[-1])
    except Exception as exc:
        raise StandaloneAccountError("AmneziaWG client key generation failed") from exc
    private = str(pair.get("private") or "").strip()
    public = str(pair.get("public") or "").strip()
    if not private or not public:
        raise StandaloneAccountError("AmneziaWG client key generation returned empty key")
    return StandaloneAccountSecret(
        protocol="amneziawg",
        subscription_id=int(subscription_id),
        username=account_username(subscription_id),
        client_private_key=private,
        client_public_key=public,
        address=_awg_address(subscription_id),
    )


async def _new_sudoku_secret(conn, subscription_id: int) -> StandaloneAccountSecret:
    raw = await cmd(conn, "/usr/local/bin/twinpanel-sudoku -keygen", timeout=60)

    def pick(label: str) -> str:
        match = re.search(re.escape(label) + r":\s*([0-9a-fA-F]+)\s*$", raw, re.M)
        if not match:
            raise StandaloneAccountError(f"Sudoku keygen missing {label}")
        return match.group(1)

    return StandaloneAccountSecret(
        protocol="sudoku",
        subscription_id=int(subscription_id),
        username=account_username(subscription_id),
        sudoku_client_key=pick("Available Private Key"),
        sudoku_master_private_key=pick("Master Private Key"),
        sudoku_master_public_key=pick("Master Public Key"),
        sudoku_port=_sudoku_port(subscription_id),
    )


async def new_account_secret(
    conn,
    protocol: str,
    subscription_id: int,
) -> StandaloneAccountSecret:
    protocol = str(protocol or "").strip().lower()
    if protocol not in STANDALONE_ACCOUNT_PROTOCOLS:
        raise StandaloneAccountError(f"unsupported standalone account protocol: {protocol}")
    if protocol == "amneziawg":
        return await _new_awg_secret(conn, subscription_id)
    if protocol == "sudoku":
        return await _new_sudoku_secret(conn, subscription_id)
    return StandaloneAccountSecret(
        protocol=protocol,
        subscription_id=int(subscription_id),
        username=account_username(subscription_id),
        password=secrets.token_urlsafe(32),
    )


async def _apply_mieru(conn, node: Node, secret: StandaloneAccountSecret, port: int) -> dict[str, Any]:
    if not secret.password:
        raise StandaloneAccountError("Mieru password is missing")
    state = f"{ACCOUNT_DIR}/mieru.json"
    config = f"{BASE_DIR}/mieru/server.json"
    script = f'''import json, os
state={state!r}
config={config!r}
username={secret.username!r}
password={secret.password!r}
os.makedirs(os.path.dirname(state), exist_ok=True)
try:
    accounts=json.load(open(state,"r",encoding="utf-8"))
except Exception:
    accounts={{}}
if not isinstance(accounts,dict): accounts={{}}
accounts[username]={{"name":username,"password":password}}
with open(state+".new","w",encoding="utf-8") as h:
    json.dump(accounts,h,separators=(",",":")); h.write("\\n")
os.chmod(state+".new",0o600); os.replace(state+".new",state)
try:
    doc=json.load(open(config,"r",encoding="utf-8"))
except Exception:
    doc={{}}
if not isinstance(doc,dict): doc={{}}
doc["users"]=list(accounts.values()) or [{{"name":{REVOCATION_SENTINEL!r},"password":__import__("secrets").token_urlsafe(48)}}]
with open(config+".account-new","w",encoding="utf-8") as h:
    json.dump(doc,h,ensure_ascii=False,indent=2); h.write("\\n")
os.chmod(config+".account-new",0o600)
'''
    await _run_python(conn, script)
    await cmd(
        conn,
        "set -eu; mita stop >/dev/null 2>&1 || true; "
        f"mita replace config {shlex.quote(config + '.account-new')} >/dev/null; "
        "mita start >/dev/null; "
        f"mv {shlex.quote(config + '.account-new')} {shlex.quote(config)}; "
        "mita status 2>&1 | grep -qi RUNNING",
        timeout=120,
    )
    host = _node_host(node)
    profile = {
        "profiles": [{
            "profileName": secret.username,
            "user": {"name": secret.username, "password": secret.password},
            "servers": [{
                "ipAddress": str(getattr(node, "public_ip", None) or host),
                "domainName": str(getattr(node, "public_domain", None) or ""),
                "portBindings": [
                    {"port": int(port), "protocol": "TCP"},
                    {"port": int(port), "protocol": "UDP"},
                ],
            }],
            "mtu": 1400,
            "multiplexing": {"level": "MULTIPLEXING_LOW"},
            "handshakeMode": "HANDSHAKE_STANDARD",
        }],
        "activeProfile": secret.username,
        "rpcPort": 8964,
        "socks5Port": 1080,
        "loggingLevel": "INFO",
        "socks5ListenLAN": False,
        "httpProxyPort": 8080,
        "httpProxyListenLAN": False,
    }
    return {
        "node_id": int(node.id), "node": str(node.name), "server": host,
        "server_ip": host, "port": int(port), "username": secret.username,
        "config_format": "mieru-json", "config": json.dumps(profile, ensure_ascii=False, indent=2),
    }


async def _remove_mieru(conn, secret: StandaloneAccountSecret) -> None:
    state = f"{ACCOUNT_DIR}/mieru.json"
    config = f"{BASE_DIR}/mieru/server.json"
    script = f'''import json, os, secrets
state={state!r}; config={config!r}; username={secret.username!r}
try: accounts=json.load(open(state,"r",encoding="utf-8"))
except Exception: accounts={{}}
if not isinstance(accounts,dict): accounts={{}}
accounts.pop(username,None)
os.makedirs(os.path.dirname(state),exist_ok=True)
with open(state+".new","w",encoding="utf-8") as h: json.dump(accounts,h,separators=(",",":")); h.write("\\n")
os.chmod(state+".new",0o600); os.replace(state+".new",state)
doc=json.load(open(config,"r",encoding="utf-8"))
doc["users"]=list(accounts.values()) or [{{"name":{REVOCATION_SENTINEL!r},"password":secrets.token_urlsafe(48)}}]
with open(config+".account-new","w",encoding="utf-8") as h: json.dump(doc,h,ensure_ascii=False,indent=2); h.write("\\n")
os.chmod(config+".account-new",0o600)
'''
    await _run_python(conn, script)
    await cmd(conn, "set -eu; mita stop >/dev/null 2>&1 || true; " + f"mita replace config {shlex.quote(config + '.account-new')} >/dev/null; mita start >/dev/null; mv {shlex.quote(config + '.account-new')} {shlex.quote(config)}", timeout=120)


async def _apply_trusttunnel(conn, node: Node, secret: StandaloneAccountSecret, port: int) -> dict[str, Any]:
    if not secret.password:
        raise StandaloneAccountError("TrustTunnel password is missing")
    state = f"{ACCOUNT_DIR}/trusttunnel.json"
    credentials = f"{BASE_DIR}/trusttunnel/credentials.toml"
    script = f'''import json, os
state={state!r}; out={credentials!r}; username={secret.username!r}; password={secret.password!r}
os.makedirs(os.path.dirname(state),exist_ok=True)
try: accounts=json.load(open(state,"r",encoding="utf-8"))
except Exception: accounts={{}}
if not isinstance(accounts,dict): accounts={{}}
accounts[username]={{"username":username,"password":password}}
with open(state+".new","w",encoding="utf-8") as h: json.dump(accounts,h,separators=(",",":")); h.write("\\n")
os.chmod(state+".new",0o600); os.replace(state+".new",state)
rows=[]
for row in accounts.values():
    rows += ["[[client]]", "username = "+json.dumps(row["username"]), "password = "+json.dumps(row["password"]), "max_http2_conns = 4", "max_http3_conns = 4", ""]
if not rows:
    rows=["[[client]]","username = "+json.dumps({REVOCATION_SENTINEL!r}),"password = "+json.dumps(__import__("secrets").token_urlsafe(48)),"max_http2_conns = 1","max_http3_conns = 1",""]
with open(out+".account-new","w",encoding="utf-8") as h: h.write("\\n".join(rows))
os.chmod(out+".account-new",0o600); os.replace(out+".account-new",out)
'''
    await _run_python(conn, script)
    await cmd(conn, "systemctl restart twinpanel-trusttunnel.service && systemctl is-active --quiet twinpanel-trusttunnel.service", timeout=120)
    host = _node_host(node)
    address = f"{host}:{int(port)}"
    raw = await cmd(
        conn,
        "cd /opt/twinpanel/trusttunnel && "
        f"./trusttunnel_endpoint {BASE_DIR}/trusttunnel/vpn.toml {BASE_DIR}/trusttunnel/hosts.toml "
        f"-c {shlex.quote(secret.username)} -a {shlex.quote(address)} --format deeplink",
        timeout=60,
    )
    deeplink = next((line.strip() for line in raw.splitlines() if line.strip().startswith("tt://")), "")
    if not deeplink:
        raise StandaloneAccountError("TrustTunnel client deeplink export failed")
    return {
        "node_id": int(node.id), "node": str(node.name), "server": host,
        "server_ip": host, "port": int(port), "username": secret.username,
        "config_format": "trusttunnel-deeplink", "config": deeplink, "uri": deeplink,
    }


async def _remove_trusttunnel(conn, secret: StandaloneAccountSecret) -> None:
    state = f"{ACCOUNT_DIR}/trusttunnel.json"
    credentials = f"{BASE_DIR}/trusttunnel/credentials.toml"
    script = f'''import json, os, secrets
state={state!r}; out={credentials!r}; username={secret.username!r}
try: accounts=json.load(open(state,"r",encoding="utf-8"))
except Exception: accounts={{}}
if not isinstance(accounts,dict): accounts={{}}
accounts.pop(username,None)
os.makedirs(os.path.dirname(state),exist_ok=True)
with open(state+".new","w",encoding="utf-8") as h: json.dump(accounts,h,separators=(",",":")); h.write("\\n")
os.chmod(state+".new",0o600); os.replace(state+".new",state)
rows=[]
for row in accounts.values(): rows += ["[[client]]","username = "+json.dumps(row["username"]),"password = "+json.dumps(row["password"]),"max_http2_conns = 4","max_http3_conns = 4",""]
if not rows: rows=["[[client]]","username = "+json.dumps({REVOCATION_SENTINEL!r}),"password = "+json.dumps(secrets.token_urlsafe(48)),"max_http2_conns = 1","max_http3_conns = 1",""]
with open(out+".new","w",encoding="utf-8") as h: h.write("\\n".join(rows))
os.chmod(out+".new",0o600); os.replace(out+".new",out)
'''
    await _run_python(conn, script)
    await cmd(conn, "systemctl restart twinpanel-trusttunnel.service", timeout=120)


async def _apply_amneziawg(conn, node: Node, secret: StandaloneAccountSecret, port: int) -> dict[str, Any]:
    if not secret.client_public_key or not secret.client_private_key or not secret.address:
        raise StandaloneAccountError("AmneziaWG peer secret is incomplete")
    state = f"{ACCOUNT_DIR}/amneziawg.json"
    config = "/etc/amnezia/amneziawg/tpawg0.conf"
    script = f'''import json, os, re
state={state!r}; config={config!r}; username={secret.username!r}
row={{"username":username,"public_key":{secret.client_public_key!r},"address":{secret.address!r}}}
os.makedirs(os.path.dirname(state),exist_ok=True)
try: accounts=json.load(open(state,"r",encoding="utf-8"))
except Exception: accounts={{}}
if not isinstance(accounts,dict): accounts={{}}
for key,value in list(accounts.items()):
    if key != username and isinstance(value,dict) and value.get("address") == row["address"]:
        raise SystemExit("amneziawg address collision")
accounts[username]=row
with open(state+".new","w",encoding="utf-8") as h: json.dump(accounts,h,separators=(",",":")); h.write("\\n")
os.chmod(state+".new",0o600); os.replace(state+".new",state)
text=open(config,"r",encoding="utf-8").read()
base=text.split("[Peer]",1)[0].rstrip()+"\\n"
base=re.sub(r"(?m)^Address\\s*=.*$","Address = 10.254.0.1/16",base)
peers=[]
for value in accounts.values():
    peers += ["","[Peer]","PublicKey = "+value["public_key"],"AllowedIPs = "+value["address"]]
with open(config+".account-new","w",encoding="utf-8") as h: h.write(base+"\\n".join(peers)+"\\n")
os.chmod(config+".account-new",0o600); os.replace(config+".account-new",config)
'''
    await _run_python(conn, script)
    await cmd(conn, "systemctl restart twinpanel-amneziawg.service && systemctl is-active --quiet twinpanel-amneziawg.service", timeout=180)
    server_private = (await cmd(conn, f"awk -F'=' '/^PrivateKey/{{sub(/^[ \\t]+/,\"\",$2); print $2; exit}}' {config}", timeout=30)).strip()
    if not server_private:
        raise StandaloneAccountError("AmneziaWG server private key unavailable")
    server_public = (await cmd(conn, f"printf '%s\\n' {shlex.quote(server_private)} | awg pubkey", timeout=30)).strip()
    host = _node_host(node)
    client = f'''[Interface]\nAddress = {secret.address}\nPrivateKey = {secret.client_private_key}\nDNS = 1.1.1.1\nJc = 6\nJmin = 8\nJmax = 80\nS1 = 64\nS2 = 96\nH1 = 101\nH2 = 202\nH3 = 303\nH4 = 404\n\n[Peer]\nPublicKey = {server_public}\nEndpoint = {host}:{int(port)}\nAllowedIPs = 0.0.0.0/0, ::/0\nPersistentKeepalive = 25\n'''
    return {
        "node_id": int(node.id), "node": str(node.name), "server": host,
        "server_ip": host, "port": int(port), "username": secret.username,
        "telemetry_identity": secret.client_public_key,
        "config_format": "amneziawg", "config": client,
    }


async def _remove_amneziawg(conn, secret: StandaloneAccountSecret) -> None:
    state = f"{ACCOUNT_DIR}/amneziawg.json"
    config = "/etc/amnezia/amneziawg/tpawg0.conf"
    script = f'''import json, os
state={state!r}; config={config!r}; username={secret.username!r}
try: accounts=json.load(open(state,"r",encoding="utf-8"))
except Exception: accounts={{}}
if not isinstance(accounts,dict): accounts={{}}
accounts.pop(username,None)
os.makedirs(os.path.dirname(state),exist_ok=True)
with open(state+".new","w",encoding="utf-8") as h: json.dump(accounts,h,separators=(",",":")); h.write("\\n")
os.chmod(state+".new",0o600); os.replace(state+".new",state)
text=open(config,"r",encoding="utf-8").read(); base=text.split("[Peer]",1)[0].rstrip()+"\\n"
peers=[]
for value in accounts.values(): peers += ["","[Peer]","PublicKey = "+value["public_key"],"AllowedIPs = "+value["address"]]
with open(config+".new","w",encoding="utf-8") as h: h.write(base+"\\n".join(peers)+"\\n")
os.chmod(config+".new",0o600); os.replace(config+".new",config)
'''
    await _run_python(conn, script)
    await cmd(conn, "systemctl restart twinpanel-amneziawg.service", timeout=180)


async def _apply_sudoku(conn, node: Node, secret: StandaloneAccountSecret, _base_port: int) -> dict[str, Any]:
    if not secret.sudoku_master_public_key or not secret.sudoku_client_key or not secret.sudoku_port:
        raise StandaloneAccountError("Sudoku per-user secret is incomplete")
    port = int(secret.sudoku_port)
    directory = f"{BASE_DIR}/sudoku/subscriptions/{int(secret.subscription_id)}"
    config = f"{directory}/server.config.json"
    service = f"twinpanel-sudoku-sub-{int(secret.subscription_id)}"
    marker = f"{directory}/subscription-id"
    await cmd(
        conn,
        "set -eu; "
        f"if ss -H -lnt | awk '$4 ~ /:{port}$/ {{found=1}} END {{exit found?0:1}}'; then "
        f"  test -f {shlex.quote(marker)} && test \"$(cat {shlex.quote(marker)})\" = {shlex.quote(str(secret.subscription_id))}; "
        "fi",
        timeout=30,
    )
    doc = {
        "mode": "server", "transport": "tcp", "local_port": port,
        "fallback_address": "127.0.0.1:80", "key": secret.sudoku_master_public_key,
        "aead": "chacha20-poly1305", "suspicious_action": "fallback",
        "padding_min": 5, "padding_max": 15, "custom_table": "", "custom_tables": [],
        "ascii": "prefer_entropy", "enable_pure_downlink": True, "multiplex": "off",
        "httpmask": {"disable": False, "mode": "auto", "tls": False, "host": "", "path_root": ""},
        "reverse": {"listen": ""},
    }
    encoded = base64.b64encode((json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode()).decode()
    unit = f'''[Unit]\nDescription=TwinPanel Sudoku subscription {secret.subscription_id}\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nUser=root\nExecStart=/usr/local/bin/twinpanel-sudoku -c {config}\nRestart=on-failure\nRestartSec=3\nLimitNOFILE=1048576\n\n[Install]\nWantedBy=multi-user.target\n'''
    unit64 = base64.b64encode(unit.encode()).decode()
    await cmd(
        conn,
        "set -eu; "
        f"install -d -m 700 {shlex.quote(directory)}; "
        f"printf '%s' {shlex.quote(encoded)} | base64 -d > {shlex.quote(config)}; chmod 600 {shlex.quote(config)}; "
        f"printf '%s\\n' {shlex.quote(str(secret.subscription_id))} > {shlex.quote(marker)}; chmod 600 {shlex.quote(marker)}; "
        f"printf '%s' {shlex.quote(unit64)} | base64 -d > /etc/systemd/system/{service}.service; "
        "systemctl daemon-reload; "
        f"systemctl enable {service}.service >/dev/null; systemctl restart {service}.service; "
        f"systemctl is-active --quiet {service}.service",
        timeout=120,
    )
    await ufw_allow(conn, port, "tcp")
    host = _node_host(node)
    client = {
        "mode": "client", "transport": "tcp", "server_address": host,
        "server_port": port, "local_address": "127.0.0.1", "local_port": 1080,
        "key": secret.sudoku_client_key, "aead": "chacha20-poly1305",
        "padding_min": 5, "padding_max": 15, "ascii": "prefer_entropy",
        "enable_pure_downlink": True, "multiplex": "off",
    }
    return {
        "node_id": int(node.id), "node": str(node.name), "server": host,
        "server_ip": host, "port": port, "username": secret.username,
        "telemetry_identity": f"sudoku-sub-{int(secret.subscription_id)}:{port}",
        "config_format": "sudoku-json", "config": json.dumps(client, ensure_ascii=False, indent=2),
    }


async def _remove_sudoku(conn, secret: StandaloneAccountSecret) -> None:
    service = f"twinpanel-sudoku-sub-{int(secret.subscription_id)}"
    directory = f"{BASE_DIR}/sudoku/subscriptions/{int(secret.subscription_id)}"
    await cmd(
        conn,
        f"systemctl disable --now {service}.service >/dev/null 2>&1 || true; "
        f"rm -f /etc/systemd/system/{service}.service; rm -rf {shlex.quote(directory)}; systemctl daemon-reload",
        check=False,
        timeout=60,
    )


async def apply_account(
    conn,
    node: Node,
    secret: StandaloneAccountSecret,
    port: int,
) -> dict[str, Any]:
    if secret.protocol == "mieru":
        return await _apply_mieru(conn, node, secret, port)
    if secret.protocol == "trusttunnel":
        return await _apply_trusttunnel(conn, node, secret, port)
    if secret.protocol == "amneziawg":
        return await _apply_amneziawg(conn, node, secret, port)
    if secret.protocol == "sudoku":
        return await _apply_sudoku(conn, node, secret, port)
    raise StandaloneAccountError(f"unsupported standalone account protocol: {secret.protocol}")


async def remove_account(conn, secret: StandaloneAccountSecret) -> None:
    if secret.protocol == "mieru":
        await _remove_mieru(conn, secret)
        return
    if secret.protocol == "trusttunnel":
        await _remove_trusttunnel(conn, secret)
        return
    if secret.protocol == "amneziawg":
        await _remove_amneziawg(conn, secret)
        return
    if secret.protocol == "sudoku":
        await _remove_sudoku(conn, secret)
        return
    raise StandaloneAccountError(f"unsupported standalone account protocol: {secret.protocol}")
