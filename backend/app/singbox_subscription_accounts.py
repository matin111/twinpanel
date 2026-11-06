from __future__ import annotations

import base64
import json
import secrets
import shlex
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from .models import Node
from .modern_protocol_runtime import CERT_PATH, CONFIG_PATH, SERVICE_NAME, STATE_PATH
from .modern_protocol_runtime_v2 import (
    SHADOWTLS_INNER_METHOD,
    SHADOWTLS_INNER_TAG,
    SINGBOX_PROTOCOLS,
    TAGS,
)
from .naive_tls_lifecycle_v224 import (
    CUSTOM_NAIVE_TRUST_MODEL,
    MANAGED_CA_CERT_PATH,
    MANAGED_NAIVE_TRUST_MODEL,
    ensure_managed_naive_tls,
)
from .routers.provision import cmd


class SingBoxAccountError(RuntimeError):
    pass


REVOCATION_SENTINEL = "__twinpanel_revoked__"


@dataclass(frozen=True)
class SingBoxAccountSecret:
    protocol: str
    username: str
    password: str
    uuid: str | None = None
    userkey: str | None = None


def account_username(subscription_id: int) -> str:
    value = int(subscription_id)
    if value <= 0:
        raise ValueError("subscription_id must be positive")
    return f"tp-sub-{value}"


def new_account_secret(protocol: str, subscription_id: int) -> SingBoxAccountSecret:
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_PROTOCOLS:
        raise SingBoxAccountError(f"unsupported sing-box account protocol: {protocol}")

    username = account_username(subscription_id)
    password = secrets.token_urlsafe(32)
    return SingBoxAccountSecret(
        protocol=protocol,
        username=username,
        password=password,
        uuid=str(uuid.uuid4()) if protocol == "tuic" else None,
        userkey=secrets.token_urlsafe(32) if protocol == "snell" else None,
    )


def secret_to_dict(secret: SingBoxAccountSecret) -> dict[str, Any]:
    return asdict(secret)


def secret_from_dict(value: dict[str, Any]) -> SingBoxAccountSecret:
    protocol = str(value.get("protocol") or "").strip().lower()
    if protocol not in SINGBOX_PROTOCOLS:
        raise SingBoxAccountError(f"unsupported sing-box account protocol: {protocol}")
    return SingBoxAccountSecret(
        protocol=protocol,
        username=str(value.get("username") or "").strip(),
        password=str(value.get("password") or ""),
        uuid=(str(value.get("uuid")) if value.get("uuid") else None),
        userkey=(str(value.get("userkey")) if value.get("userkey") else None),
    )


def _user_record(secret: SingBoxAccountSecret) -> dict[str, str]:
    if secret.protocol == "tuic":
        if not secret.uuid:
            raise SingBoxAccountError("TUIC UUID is missing")
        return {
            "name": secret.username,
            "uuid": secret.uuid,
            "password": secret.password,
        }
    if secret.protocol == "naive":
        return {
            "username": secret.username,
            "password": secret.password,
        }
    if secret.protocol == "snell":
        if not secret.userkey:
            raise SingBoxAccountError("Snell user key is missing")
        return {
            "name": secret.username,
            "userkey": secret.userkey,
        }
    return {
        "name": secret.username,
        "password": secret.password,
    }


def _mutation_script(
    protocol: str,
    username: str,
    record: dict[str, str] | None,
) -> str:
    tag = TAGS[protocol]
    record_json = json.dumps(record, ensure_ascii=False) if record is not None else "null"
    return f'''from __future__ import annotations
import json
import os
import secrets
import uuid
import copy

CONFIG = {CONFIG_PATH!r}
STATE = {STATE_PATH!r}
TAG = {tag!r}
PROTOCOL = {protocol!r}
USERNAME = {username!r}
RECORD = json.loads({record_json!r})
SENTINEL = {REVOCATION_SENTINEL!r}
SHADOWTLS_INNER_TAG = {SHADOWTLS_INNER_TAG!r}
SHADOWTLS_INNER_METHOD = {SHADOWTLS_INNER_METHOD!r}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


with open(CONFIG, "r", encoding="utf-8") as handle:
    doc = json.load(handle)
if not isinstance(doc, dict):
    raise SystemExit("sing-box config is not an object")
original_doc = copy.deepcopy(doc)

inbounds = doc.get("inbounds")
if not isinstance(inbounds, list):
    raise SystemExit("sing-box inbounds are missing")

inbound = next(
    (
        item for item in inbounds
        if isinstance(item, dict)
        and item.get("tag") == TAG
        and item.get("type") == PROTOCOL
    ),
    None,
)
if not isinstance(inbound, dict):
    raise SystemExit("managed protocol inbound is not installed")

users = inbound.get("users")
if not isinstance(users, list):
    users = []
installed_users = list(users)

key = "username" if PROTOCOL == "naive" else "name"
users = [
    item for item in users
    if not (
        isinstance(item, dict)
        and (
            str(item.get(key) or "") == USERNAME
            or str(item.get(key) or "").startswith(SENTINEL)
        )
    )
]
if RECORD is not None:
    users.append(RECORD)

# Revoking the last real subscriber must not make the shared inbound
# unauthenticated and must not fail the revoke operation. Keep one random,
# undisclosed sentinel credential which is removed automatically as soon as a
# real subscriber is provisioned again.
if not users:
    sentinel_password = secrets.token_urlsafe(48)
    if PROTOCOL == "tuic":
        users = [dict(
            name=SENTINEL,
            uuid=str(uuid.uuid4()),
            password=sentinel_password,
        )]
    elif PROTOCOL == "naive":
        users = [dict(
            username=SENTINEL,
            password=sentinel_password,
        )]
    elif PROTOCOL == "snell":
        users = [dict(
            name=SENTINEL,
            userkey=secrets.token_urlsafe(48),
        )]
    else:
        users = [dict(
            name=SENTINEL,
            password=sentinel_password,
        )]

inbound["users"] = users
if RECORD is not None:
    old_matches = [u for u in installed_users if isinstance(u, dict)
                   and str(u.get(key) or "") == USERNAME]
    old_revoked = any(
        isinstance(u, dict) and str(u.get(key) or "").startswith(SENTINEL)
        for u in installed_users
    )
    # A replay of the same credential must not reorder an inbound's users.
    if len(old_matches) == 1 and old_matches[0] == RECORD and not old_revoked:
        inbound["users"] = installed_users

if PROTOCOL == "shadowtls":
    state = load_json(STATE, {{}})
    if not isinstance(state, dict):
        state = {{}}
    seed = state.get("shadowtls")
    if not isinstance(seed, dict):
        seed = {{}}
    # Inner proxy auth is node runtime state. It is intentionally separate from
    # the per-subscription ShadowTLS v3 password and therefore never rotates a
    # customer's credential during reconcile/self-heal.
    seed.setdefault("inner_password", secrets.token_urlsafe(32))
    state["shadowtls"] = seed

    inbound["detour"] = SHADOWTLS_INNER_TAG
    fresh_inner = dict(
        type="shadowsocks",
        tag=SHADOWTLS_INNER_TAG,
        listen="127.0.0.1",
        method=SHADOWTLS_INNER_METHOD,
        password=seed["inner_password"],
    )
    inner = next(
        (
            item for item in inbounds
            if isinstance(item, dict)
            and item.get("tag") == SHADOWTLS_INNER_TAG
        ),
        None,
    )
    if isinstance(inner, dict):
        inner.clear()
        inner.update(fresh_inner)
    else:
        inbounds.append(fresh_inner)

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".account-new", "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")
    os.replace(STATE + ".account-new", STATE)
    os.chmod(STATE, 0o600)

if doc == original_doc:
    print("account_unchanged=1")
    raise SystemExit(0)

with open(CONFIG + ".account-new", "w", encoding="utf-8") as handle:
    json.dump(doc, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")
os.chmod(CONFIG + ".account-new", 0o600)
print("account_users=" + str(len(users)))
'''


def _snapshot_script(protocol: str) -> str:
    tag = TAGS[protocol]
    return f'''import json
p={CONFIG_PATH!r}
tag={tag!r}
protocol={protocol!r}
inner_tag={SHADOWTLS_INNER_TAG!r}
with open(p, "r", encoding="utf-8") as h:
    d=json.load(h)
row=next((x for x in d.get("inbounds",[]) if isinstance(x,dict) and x.get("tag")==tag),None)
if not isinstance(row,dict):
    raise SystemExit("managed inbound not found")
if protocol == "shadowtls":
    inner=next((x for x in d.get("inbounds",[]) if isinstance(x,dict) and x.get("tag")==inner_tag and x.get("type")=="shadowsocks"),None)
    if not isinstance(inner,dict) or not inner.get("method") or not inner.get("password"):
        raise SystemExit("managed ShadowTLS inner inbound not found")
    row=dict(row)
    row["_twinpanel_shadowtls_inner"]={{"method":inner["method"],"password":inner["password"]}}
print(json.dumps(row,separators=(",",":")))
'''


async def _commit_account_config(conn, script: str) -> None:
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    backup = f"{CONFIG_PATH}.bak-account-$(date +%Y%m%d-%H%M%S)"
    await cmd(
        conn,
        "set -eu; exec 9>/run/twinpanel-singbox-batch.lock; flock -x 9; "
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3; "
        f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.account-new')}; "
        f"cp -a {shlex.quote(CONFIG_PATH)} {backup}; "
        f"mv {shlex.quote(CONFIG_PATH + '.account-new')} {shlex.quote(CONFIG_PATH)}; "
        f"if ! systemctl restart {SERVICE_NAME}.service; then "
        f"  last=$(ls -1t {shlex.quote(CONFIG_PATH)}.bak-account-* | head -n1); "
        f"  cp -a \"$last\" {shlex.quote(CONFIG_PATH)}; "
        f"  systemctl restart {SERVICE_NAME}.service || true; "
        f"  exit 1; "
        f"fi; "
        f"systemctl is-active --quiet {SERVICE_NAME}.service",
        timeout=120,
    )


async def read_inbound(conn, protocol: str) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_PROTOCOLS:
        raise SingBoxAccountError(f"unsupported sing-box account protocol: {protocol}")
    raw = await cmd(conn, f"python3 - <<'PY'\n{_snapshot_script(protocol)}PY")
    try:
        value = json.loads(raw.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise SingBoxAccountError("could not read managed inbound") from exc
    if not isinstance(value, dict):
        raise SingBoxAccountError("managed inbound snapshot is invalid")
    return value


async def _read_certificate(conn, path: str, *, label: str) -> str:
    raw = await cmd(conn, f"cat -- {shlex.quote(path)}")
    certificate = str(raw or "").strip()
    if "-----BEGIN CERTIFICATE-----" not in certificate or "-----END CERTIFICATE-----" not in certificate:
        raise SingBoxAccountError(f"{label} certificate is invalid")
    return certificate + "\n"


async def _naive_tls_trust_material(
    conn,
    node: Node,
    inbound: dict[str, Any],
) -> tuple[str, str]:
    server_tls = inbound.get("tls") if isinstance(inbound.get("tls"), dict) else {}
    cert_path = str(server_tls.get("certificate_path") or "").strip()
    if not cert_path:
        raise SingBoxAccountError("Naive TLS certificate path is missing")

    if cert_path == CERT_PATH:
        await ensure_managed_naive_tls(conn, node)
        trust_path = MANAGED_CA_CERT_PATH
        trust_model = MANAGED_NAIVE_TRUST_MODEL
    else:
        # Preserve existing custom-certificate behavior. Custom TLS material is
        # operator-owned and is never rotated by the managed lifecycle.
        trust_path = cert_path
        trust_model = CUSTOM_NAIVE_TRUST_MODEL

    certificate = await _read_certificate(
        conn,
        trust_path,
        label="Naive TLS trust",
    )
    return certificate, trust_model


async def apply_account(
    conn,
    node: Node,
    secret: SingBoxAccountSecret,
) -> dict[str, Any]:
    if secret.protocol not in SINGBOX_PROTOCOLS:
        raise SingBoxAccountError(f"unsupported sing-box account protocol: {secret.protocol}")
    if not secret.username or not secret.password:
        raise SingBoxAccountError("account secret is incomplete")

    await _commit_account_config(
        conn,
        _mutation_script(
            secret.protocol,
            secret.username,
            _user_record(secret),
        ),
    )
    inbound = await read_inbound(conn, secret.protocol)
    tls_certificate = None
    tls_trust_model = None
    if secret.protocol == "naive":
        tls_certificate, tls_trust_model = await _naive_tls_trust_material(
            conn,
            node,
            inbound,
        )
    return client_item(
        node,
        secret,
        inbound,
        tls_certificate=tls_certificate,
        tls_trust_model=tls_trust_model,
    )


def _batch_mutation_script(secrets: list[SingBoxAccountSecret]) -> str:
    """One safe config rewrite and restart for a bounded set of sing-box users."""
    if not secrets or len(secrets) > 150:
        raise SingBoxAccountError("sing-box batch must contain 1..150 accounts")
    updates = []
    for secret in secrets:
        if secret.protocol not in SINGBOX_PROTOCOLS or not secret.username or not secret.password:
            raise SingBoxAccountError("invalid sing-box account in batch")
        updates.append({"protocol": secret.protocol, "tag": TAGS[secret.protocol],
                        "username": secret.username, "record": _user_record(secret)})
    payload = json.dumps(updates, ensure_ascii=False)
    return f'''import json, os, secrets, fcntl, copy

CONFIG = {CONFIG_PATH!r}
STATE = {STATE_PATH!r}
UPDATES = json.loads({payload!r})
SENTINEL = {REVOCATION_SENTINEL!r}
SHADOWTLS_INNER_TAG = {SHADOWTLS_INNER_TAG!r}
SHADOWTLS_INNER_METHOD = {SHADOWTLS_INNER_METHOD!r}

with open(CONFIG, "r", encoding="utf-8") as handle:
    doc = json.load(handle)
original_doc = copy.deepcopy(doc)
inbounds = doc.get("inbounds")
if not isinstance(inbounds, list):
    raise SystemExit("managed inbounds are unavailable")
inner_secret = None
for operation in UPDATES:
    protocol = operation["protocol"]
    inbound = next((row for row in inbounds if isinstance(row, dict)
                    and row.get("tag") == operation["tag"]
                    and row.get("type") == protocol), None)
    if not isinstance(inbound, dict):
        raise SystemExit("managed inbound not found: " + protocol)
    key = "username" if protocol == "naive" else "name"
    users = inbound.get("users")
    users = list(users) if isinstance(users, list) else []
    matching = [u for u in users if isinstance(u, dict) and
                str(u.get(key) or "") == operation["username"]]
    revoked = any(isinstance(u, dict) and
                  str(u.get(key) or "").startswith(SENTINEL) for u in users)
    # Do not reorder an existing identical credential: it would cause a
    # needless restart even though authentication is unchanged.
    if len(matching) != 1 or matching[0] != operation["record"] or revoked:
        users = [u for u in users if not (isinstance(u, dict) and
                 (str(u.get(key) or "") == operation["username"] or
                  str(u.get(key) or "").startswith(SENTINEL)))]
        users.append(operation["record"])
        inbound["users"] = users
    if protocol == "shadowtls":
        state = dict(json.load(open(STATE, encoding="utf-8"))) if os.path.exists(STATE) else {{}}
        shadow = dict(state.get("shadowtls") or {{}})
        shadow.setdefault("inner_password", secrets.token_urlsafe(32))
        inner_secret = shadow["inner_password"]
        inbound["detour"] = SHADOWTLS_INNER_TAG
        inner = dict(type="shadowsocks", tag=SHADOWTLS_INNER_TAG,
                     listen="127.0.0.1", method=SHADOWTLS_INNER_METHOD,
                     password=inner_secret)
        previous = next((row for row in inbounds if isinstance(row, dict)
                         and row.get("tag") == SHADOWTLS_INNER_TAG), None)
        if previous is None:
            inbounds.append(inner)
        else:
            previous.clear()
            previous.update(inner)
        state["shadowtls"] = shadow

# No-op: do not touch the node config or service; the SSH shell checks
# this marker under the per-node flock before skipping a restart.
if doc == original_doc:
    print("batch_unchanged=1")
    raise SystemExit(0)

with open(CONFIG + ".account-new", "w", encoding="utf-8") as handle:
    json.dump(doc, handle, ensure_ascii=False, indent=2)
    handle.write("\\n")
os.chmod(CONFIG + ".account-new", 0o600)
if inner_secret is not None:
    with open(STATE + ".account-new", "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")
    os.chmod(STATE + ".account-new", 0o600)
print("batch_users=" + str(len(UPDATES)))
'''


async def apply_accounts_batch(
    conn, node: Node, secrets: list[SingBoxAccountSecret],
) -> list[dict[str, Any]]:
    """Apply up to 40 independent users with one validate/restart.

    Does not change the existing single-user paths. On validation or restart
    failure, restore the previous config before returning an error.
    """
    script = _batch_mutation_script(secrets)
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    command = (
        "set -eu; "
        "exec 9>/run/twinpanel-singbox-batch.lock; flock -x 9; "
        f"result=$(printf '%s' {shlex.quote(encoded)} | base64 -d | python3); "
        "if [ \"$result\" = 'batch_unchanged=1' ]; then "
        # Keep the running service untouched on no-op. If the service has
        # stopped, start it even if its installed credential set is correct.
        f"systemctl is-active --quiet {SERVICE_NAME}.service || systemctl restart {SERVICE_NAME}.service; "
        "else "
        f"/usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.account-new')}; "
        f"backup=$(mktemp {shlex.quote(CONFIG_PATH + '.batch-backup-XXXXXX')}); "
        f"cp -a {shlex.quote(CONFIG_PATH)} \"$backup\"; "
        f"mv {shlex.quote(CONFIG_PATH + '.account-new')} {shlex.quote(CONFIG_PATH)}; "
        f"if ! systemctl restart {SERVICE_NAME}.service; then "
        f"cp -a \"$backup\" {shlex.quote(CONFIG_PATH)}; "
        f"systemctl restart {SERVICE_NAME}.service || true; exit 1; fi; "
        f"if test -f {shlex.quote(STATE_PATH + '.account-new')}; then "
        f"mv {shlex.quote(STATE_PATH + '.account-new')} {shlex.quote(STATE_PATH)}; fi; "
        "rm -f \"$backup\"; "
        "fi; "
        f"systemctl is-active --quiet {SERVICE_NAME}.service"
    )
    await cmd(conn, command, timeout=180)
    inbounds: dict[str, dict[str, Any]] = {}
    for protocol in dict.fromkeys(secret.protocol for secret in secrets):
        inbounds[protocol] = await read_inbound(conn, protocol)
    results = []
    for secret in secrets:
        certificate = None
        trust_model = None
        if secret.protocol == "naive":
            certificate, trust_model = await _naive_tls_trust_material(
                conn, node, inbounds[secret.protocol]
            )
        results.append(client_item(
            node, secret, inbounds[secret.protocol],
            tls_certificate=certificate, tls_trust_model=trust_model,
        ))
    return results


async def remove_account(
    conn,
    protocol: str,
    subscription_id: int,
) -> None:
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_PROTOCOLS:
        raise SingBoxAccountError(f"unsupported sing-box account protocol: {protocol}")
    await _commit_account_config(
        conn,
        _mutation_script(protocol, account_username(subscription_id), None),
    )


def _node_host(node: Node) -> str:
    return str(getattr(node, "public_domain", None) or getattr(node, "public_ip", "") or "").strip()


def _client_tls(node: Node, inbound: dict[str, Any], *, server_name: str | None = None) -> dict[str, Any]:
    host = str(server_name or getattr(node, "public_domain", None) or getattr(node, "public_ip", "") or "").strip()
    server_tls = inbound.get("tls") if isinstance(inbound.get("tls"), dict) else {}
    cert_path = str(server_tls.get("certificate_path") or "")
    trusted_custom_cert = bool(
        getattr(node, "public_domain", None)
        and cert_path
        and cert_path != CERT_PATH
    )
    return {
        "enabled": True,
        "server_name": host,
        "insecure": not trusted_custom_cert,
    }


def _naive_tls_requires_repair(tls: Any, trust_model: str) -> bool:
    if not isinstance(tls, dict):
        return True
    if "insecure" in tls:
        return True
    certificate = str(tls.get("certificate") or "").strip()
    if not certificate:
        return True
    return trust_model not in {
        MANAGED_NAIVE_TRUST_MODEL,
        CUSTOM_NAIVE_TRUST_MODEL,
    }


def naive_client_item_requires_repair(item: dict[str, Any]) -> bool:
    """Detect Naive payloads that cannot authenticate the managed TLS endpoint.

    Naive outbound has a restricted TLS schema and rejects tls.insecure. Managed
    TwinPanel TLS therefore carries a stable local CA while the server uses a
    short-lived CA-signed leaf. Legacy payloads with insecure, missing trust, or
    the rc.223 leaf-pin model are refreshed without rotating account identity.
    """

    if not isinstance(item, dict):
        return False

    trust_model = str(item.get("tls_trust_model") or "").strip()

    outbound = item.get("outbound")
    if isinstance(outbound, dict) and str(outbound.get("type") or "").lower() == "naive":
        return _naive_tls_requires_repair(outbound.get("tls"), trust_model)

    raw_config = str(item.get("config") or "").strip()
    if not raw_config:
        return False

    try:
        config = json.loads(raw_config)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False

    outbounds = config.get("outbounds") if isinstance(config, dict) else None
    if not isinstance(outbounds, list):
        return False

    for candidate in outbounds:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("type") or "").lower() != "naive":
            continue
        return _naive_tls_requires_repair(candidate.get("tls"), trust_model)

    return False


def client_outbound(
    node: Node,
    secret: SingBoxAccountSecret,
    inbound: dict[str, Any],
    *,
    server: str | None = None,
    port: int | None = None,
    tls_certificate: str | None = None,
) -> dict[str, Any]:
    protocol = secret.protocol
    host = str(server or _node_host(node)).strip()
    listen_port = int(port or inbound.get("listen_port") or 0)
    if not host or not 1 <= listen_port <= 65535:
        raise SingBoxAccountError("client endpoint is incomplete")

    out: dict[str, Any] = {
        "type": protocol,
        "tag": f"twinpanel-{protocol}",
        "server": host,
        "server_port": listen_port,
    }

    if protocol == "hysteria2":
        out["password"] = secret.password
        if isinstance(inbound.get("obfs"), dict):
            out["obfs"] = dict(inbound["obfs"])
        profile = str(inbound.get("bbr_profile") or "").strip()
        if profile:
            out["bbr_profile"] = profile
        out["tls"] = _client_tls(node, inbound)

    elif protocol == "tuic":
        if not secret.uuid:
            raise SingBoxAccountError("TUIC UUID is missing")
        out.update({
            "uuid": secret.uuid,
            "password": secret.password,
            "congestion_control": str(inbound.get("congestion_control") or "cubic"),
            "zero_rtt_handshake": bool(inbound.get("zero_rtt_handshake", False)),
            "heartbeat": str(inbound.get("heartbeat") or "10s"),
            "tls": _client_tls(node, inbound),
        })

    elif protocol == "anytls":
        out.update({
            "password": secret.password,
            "tls": _client_tls(node, inbound),
        })

    elif protocol == "naive":
        tls = _client_tls(node, inbound)
        # Naive does not accept tls.insecure. Keep certificate verification on
        # and provide explicit trust material (managed CA or custom certificate).
        tls.pop("insecure", None)
        certificate = str(tls_certificate or "").strip()
        if certificate:
            tls["certificate"] = certificate + "\n"
        out.update({
            "username": secret.username,
            "password": secret.password,
            "quic_congestion_control": str(inbound.get("quic_congestion_control") or "bbr"),
            "tls": tls,
        })
        if str(inbound.get("network") or "").lower() == "udp":
            out["quic"] = True

    elif protocol == "shadowtls":
        handshake = inbound.get("handshake") if isinstance(inbound.get("handshake"), dict) else {}
        handshake_server = str(handshake.get("server") or "www.microsoft.com")
        out.update({
            "version": int(inbound.get("version") or 3),
            "password": secret.password,
            "tls": _client_tls(node, inbound, server_name=handshake_server),
        })

    elif protocol == "snell":
        if not secret.userkey:
            raise SingBoxAccountError("Snell user key is missing")
        version = int(inbound.get("version") or 6)
        out.update({
            "version": 4 if version == 5 else version,
            "psk": str(inbound.get("psk") or ""),
            "userkey": secret.userkey,
        })
        if not out["psk"]:
            raise SingBoxAccountError("Snell server PSK is missing")
        if version == 6:
            out["mode"] = str(inbound.get("mode") or "default")
        else:
            out["obfs_mode"] = str(inbound.get("obfs_mode") or "none")

    else:
        raise SingBoxAccountError(f"unsupported sing-box account protocol: {protocol}")

    return out


def client_item(
    node: Node,
    secret: SingBoxAccountSecret,
    inbound: dict[str, Any],
    *,
    server: str | None = None,
    port: int | None = None,
    tls_certificate: str | None = None,
    tls_trust_model: str | None = None,
) -> dict[str, Any]:
    outbound = client_outbound(
        node,
        secret,
        inbound,
        server=server,
        port=port,
        tls_certificate=tls_certificate,
    )

    endpoint_server = str(outbound["server"])
    endpoint_port = int(outbound["server_port"])
    config_outbounds = [outbound]
    route_final = outbound["tag"]

    if secret.protocol == "shadowtls":
        inner = inbound.get("_twinpanel_shadowtls_inner")
        if not isinstance(inner, dict):
            raise SingBoxAccountError("ShadowTLS inner proxy snapshot is missing")
        method = str(inner.get("method") or "").strip()
        password = str(inner.get("password") or "")
        if not method or not password:
            raise SingBoxAccountError("ShadowTLS inner proxy credential is incomplete")

        transport = dict(outbound)
        transport["tag"] = "twinpanel-shadowtls-transport"
        proxy = {
            "type": "shadowsocks",
            "tag": "twinpanel-shadowtls",
            "method": method,
            "password": password,
            "detour": transport["tag"],
            "udp_over_tcp": {"enabled": True, "version": 2},
        }
        config_outbounds = [proxy, transport]
        route_final = proxy["tag"]
        # Preserve the public protocol metadata as ShadowTLS. Consumers that
        # import raw sing-box JSON receive the complete two-stage chain.
        outbound = transport

    config = {
        "log": {"level": "warn"},
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 2080,
            }
        ],
        "outbounds": config_outbounds,
        "route": {"final": route_final},
    }
    item = {
        "node_id": int(node.id),
        "node": str(node.name),
        "server": endpoint_server,
        "server_ip": endpoint_server,
        "port": endpoint_port,
        "username": secret.username,
        "config_format": "sing-box",
        "config": json.dumps(config, ensure_ascii=False, indent=2),
        "outbound": outbound,
    }
    if secret.protocol == "naive" and tls_trust_model:
        item["tls_trust_model"] = str(tls_trust_model)
    return item