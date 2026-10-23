from __future__ import annotations

import asyncio
import base64
import logging
import re
import shlex
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_

from ..database import SessionLocal
from ..models import Node, NodeProtocolConfig, ProtocolCredential
from ..quota_models import QuotaNodeCommand
from ..protocol_identity import is_openvpn_central_pki_enabled
from .. import subscription_enforcement as enforcement


logger = logging.getLogger(__name__)

SINGBOX_MODERN_PROTOCOLS = frozenset(
    {"hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell"}
)
STANDALONE_MODERN_PROTOCOLS = frozenset(
    {"mieru", "trusttunnel", "amneziawg", "sudoku"}
)
CONTROLLER_MODERN_PROTOCOLS = SINGBOX_MODERN_PROTOCOLS | STANDALONE_MODERN_PROTOCOLS

# Commands are queued with the node/Agent protocol name, not necessarily the
# panel/database protocol name. Keep this mapping explicit so the worker always
# resolves the exact ProtocolCredential row which owns the stored identity.
CLASSIC_SOURCE_PROTOCOL = {
    "openconnect": "cisco",
    "openvpn": "openvpn",
    "wireguard": "wireguard",
    "l2tp": "l2tp",
    "xray": "v2ray",
}
CONTROLLER_CLASSIC_PROTOCOLS = frozenset(CLASSIC_SOURCE_PROTOCOL)
CONTROLLER_ACCOUNT_PROTOCOLS = CONTROLLER_MODERN_PROTOCOLS | CONTROLLER_CLASSIC_PROTOCOLS

_MODERN_EXECUTOR = "controller-modern-v1"
_CLASSIC_EXECUTOR = "controller-classic-v2"
_PROCESSING_TIMEOUT_SECONDS = 90
_MAX_ATTEMPTS = 5
_installed = False
_original_queue = None


def _command_protocol(command: QuotaNodeCommand) -> str:
    payload = command.payload if isinstance(command.payload, dict) else {}
    return str(payload.get("protocol") or "").strip().lower()


def _executor_for_protocol(protocol: str) -> str | None:
    if protocol in CONTROLLER_MODERN_PROTOCOLS:
        return _MODERN_EXECUTOR
    if protocol in CONTROLLER_CLASSIC_PROTOCOLS:
        return _CLASSIC_EXECUTOR
    return None


def install_account_enforcement_hooks() -> None:
    """Route all 15 account protocols to durable controller-owned workers.

    Modern account enforcement was already controller-owned in V1. Classic
    enforcement used to leave QuotaNodeCommand rows in Agent `pending`, while
    the shipped TwinPanel node Agent had no quota-command poll/execute loop and
    the command payload did not contain enough credential identity to safely
    reconstruct Cisco/L2TP/WireGuard state. V2 therefore keeps credentials on
    the controller and performs exact revoke/restore over the existing saved SSH
    management channel.
    """

    global _installed, _original_queue
    if _installed:
        return

    # Modern protocols have no legacy Agent aliases; register them so the
    # canonical enforcement resolver can target their provisioned credentials.
    enforcement.AGENT_PROTOCOL.update(
        {protocol: protocol for protocol in CONTROLLER_MODERN_PROTOCOLS}
    )
    enforcement.SESSION_ALIASES.update(
        {protocol: {protocol} for protocol in CONTROLLER_MODERN_PROTOCOLS}
    )

    original = enforcement.queue_subscription_enforcement
    _original_queue = original

    def controller_aware_queue(
        db,
        subscription,
        *,
        command_type: str,
        reason: str,
        protocols: list[str] | None = None,
        node_ids: list[int] | None = None,
    ) -> dict:
        result = original(
            db,
            subscription,
            command_type=command_type,
            reason=reason,
            protocols=protocols,
            node_ids=node_ids,
        )

        command_ids = [
            str(item.get("command_id") or "")
            for item in result.get("commands", [])
            if item.get("command_id")
        ]
        if not command_ids:
            return result

        db.flush()
        rows = (
            db.query(QuotaNodeCommand)
            .filter(QuotaNodeCommand.command_id.in_(command_ids))
            .all()
        )
        for row in rows:
            protocol = _command_protocol(row)
            executor = _executor_for_protocol(protocol)
            if executor is None:
                continue
            payload = dict(row.payload or {})
            payload["executor"] = executor
            row.payload = payload
            # Agent pull only consumes status=pending. Controller-owned work is
            # durable and cannot race a node Agent or leak account secrets into
            # the node command payload.
            row.status = "controller_pending"

        return result

    enforcement.queue_subscription_enforcement = controller_aware_queue
    _installed = True


def _claim_next_command() -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        stale_before = now - timedelta(seconds=_PROCESSING_TIMEOUT_SECONDS)
        row = (
            db.query(QuotaNodeCommand)
            .filter(
                QuotaNodeCommand.expires_at > now,
                or_(
                    QuotaNodeCommand.status == "controller_pending",
                    and_(
                        QuotaNodeCommand.status == "controller_processing",
                        QuotaNodeCommand.last_delivered_at.isnot(None),
                        QuotaNodeCommand.last_delivered_at < stale_before,
                    ),
                ),
            )
            .order_by(QuotaNodeCommand.issued_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            db.rollback()
            return None

        protocol = _command_protocol(row)
        payload = dict(row.payload or {})
        expected_executor = _executor_for_protocol(protocol)
        if expected_executor is None or payload.get("executor") != expected_executor:
            row.status = "failed"
            row.result_code = "controller_protocol_mismatch"
            row.result_message = "command is not owned by account enforcement V2"
            row.acknowledged_at = now
            db.commit()
            return None

        row.status = "controller_processing"
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.last_delivered_at = now
        snapshot = {
            "command_id": str(row.command_id),
            "node_id": int(row.node_id),
            "command_type": str(row.command_type),
            "subscription_id": int(payload.get("subscription_id") or 0),
            "protocol": protocol,
            "executor": expected_executor,
            "attempt": int(row.attempt_count),
        }
        db.commit()
        return snapshot
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _decode_modern_secret(protocol: str, credential: ProtocolCredential):
    from ..routers import account_delivery as account_delivery

    decoded = account_delivery._dec(credential.secret_encrypted)
    if not isinstance(decoded, dict):
        raise RuntimeError("stored protocol credential is invalid")

    if protocol in SINGBOX_MODERN_PROTOCOLS:
        from ..singbox_subscription_accounts import secret_from_dict
    else:
        from ..standalone_subscription_accounts import secret_from_dict

    secret = secret_from_dict(decoded)
    if str(secret.protocol) != protocol:
        raise RuntimeError("stored protocol credential protocol mismatch")
    return secret


def _decoded_classic_items(credential: ProtocolCredential) -> list[dict[str, Any]]:
    from ..routers import account_delivery as account_delivery

    decoded = account_delivery._dec(credential.config_text_encrypted)
    if not isinstance(decoded, list):
        raise RuntimeError("stored classic connection items are unavailable")
    return [item for item in decoded if isinstance(item, dict)]


def _classic_item_for_node(
    credential: ProtocolCredential,
    node_id: int,
) -> dict[str, Any]:
    for item in _decoded_classic_items(credential):
        try:
            item_node_id = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            item_node_id = 0
        if item_node_id == int(node_id):
            return item
    raise RuntimeError("stored classic node credential is unavailable")


def _decoded_password(credential: ProtocolCredential) -> str:
    from ..routers import account_delivery as account_delivery

    decoded = account_delivery._dec(credential.secret_encrypted)
    if not isinstance(decoded, dict):
        raise RuntimeError("stored account password is unavailable")
    password = str(decoded.get("password") or "")
    if not password:
        raise RuntimeError("stored account password is unavailable")
    return password


async def _remote_run(conn, command: str, *, check: bool = True, timeout: int = 30):
    result = await conn.run(command, check=False, timeout=timeout)
    if check and int(result.exit_status or 0) != 0:
        message = str(result.stderr or result.stdout or "").strip()
        raise RuntimeError(message or f"remote command failed ({result.exit_status})")
    return result


async def _classic_cisco(
    conn,
    credential: ProtocolCredential,
    command_type: str,
) -> str:
    username = str(credential.username or "").strip()
    if not username or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", username):
        raise RuntimeError("stored Cisco username is unavailable")

    if command_type == "revoke_subscription":
        await _remote_run(
            conn,
            "ocpasswd -c /etc/ocserv/ocpasswd -d "
            + shlex.quote(username)
            + " >/dev/null 2>&1 || true; "
            + "occtl disconnect user "
            + shlex.quote(username)
            + " >/dev/null 2>&1 || true",
            check=False,
        )
        return "controller_classic_revoked"

    if command_type != "restore_subscription":
        raise RuntimeError(f"unsupported command type: {command_type}")

    password = _decoded_password(credential)
    encoded = base64.b64encode((password + "\n" + password + "\n").encode()).decode()
    await _remote_run(
        conn,
        "printf '%s' "
        + shlex.quote(encoded)
        + " | base64 -d | ocpasswd -c /etc/ocserv/ocpasswd "
        + shlex.quote(username),
    )
    return "controller_classic_restored"


def _openvpn_common_name(db, subscription_id: int, node_id: int) -> str:
    if is_openvpn_central_pki_enabled(db):
        return f"mv-sub-{int(subscription_id)}"
    return f"mv{int(subscription_id)}n{int(node_id)}"


async def _classic_openvpn(
    conn,
    db,
    subscription_id: int,
    node_id: int,
    command_type: str,
) -> str:
    common_name = _openvpn_common_name(db, subscription_id, node_id)
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", common_name):
        raise RuntimeError("OpenVPN common-name is invalid")

    marker = f"/etc/openvpn/twinpanel-disabled/{common_name}"

    if command_type == "restore_subscription":
        await _remote_run(
            conn,
            "mkdir -p /etc/openvpn/twinpanel-disabled && rm -f "
            + shlex.quote(marker),
        )
        return "controller_classic_restored"

    if command_type != "revoke_subscription":
        raise RuntimeError(f"unsupported command type: {command_type}")

    # The existing OpenVPN client-connect hook rejects any CN with this marker.
    # Kill an already connected instance through the configured management Unix
    # socket so revoke is immediate as well as persistent across reconnects.
    await _remote_run(
        conn,
        "mkdir -p /etc/openvpn/twinpanel-disabled && touch "
        + shlex.quote(marker),
    )
    script = f'''import socket\npath="/run/openvpn-server/twinpanel-mgmt.sock"\ncn={common_name!r}\ns=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\ns.settimeout(3)\ntry:\n s.connect(path)\n try: s.recv(65536)\n except Exception: pass\n s.sendall(("kill "+cn+"\\nquit\\n").encode())\n try: s.recv(65536)\n except Exception: pass\nfinally:\n s.close()\n'''
    encoded = base64.b64encode(script.encode()).decode()
    await _remote_run(
        conn,
        "printf '%s' " + shlex.quote(encoded) + " | base64 -d | python3",
        check=False,
    )
    return "controller_classic_revoked"


async def _wireguard_public_key(conn, private_key: str) -> str:
    result = await conn.run(
        "wg pubkey",
        input=private_key.strip() + "\n",
        check=False,
        timeout=10,
    )
    if int(result.exit_status or 0) != 0:
        raise RuntimeError(str(result.stderr or result.stdout or "wg pubkey failed")[:700])
    public_key = str(result.stdout or "").strip()
    if not public_key:
        raise RuntimeError("stored WireGuard public key cannot be derived")
    return public_key


def _wireguard_identity(item: dict[str, Any]) -> tuple[str, str]:
    config = str(item.get("config") or "")
    private_match = re.search(r"(?m)^PrivateKey\s*=\s*(\S+)\s*$", config)
    address_match = re.search(r"(?m)^Address\s*=\s*([0-9.]+/\d+)\s*$", config)
    private_key = str(private_match.group(1) if private_match else "").strip()
    address = str(item.get("address") or (address_match.group(1) if address_match else "")).strip()
    if not private_key or not address:
        raise RuntimeError("stored WireGuard identity is incomplete")
    return private_key, address


async def _persist_wireguard_peer(
    conn,
    *,
    public_key: str,
    address: str,
    enabled: bool,
) -> None:
    script = f'''from pathlib import Path\nimport re\npath=Path("/etc/wireguard/wg-access0.conf")\ntext=path.read_text(encoding="utf-8") if path.exists() else ""\npub={public_key!r}\naddress={address!r}\nparts=re.split(r"(?m)(?=^\\[Peer\\]\\s*$)", text)\nhead=parts[0] if parts else text\npeers=[]\nfor block in parts[1:]:\n    if re.search(r"(?m)^PublicKey\\s*=\\s*"+re.escape(pub)+r"\\s*$", block):\n        continue\n    peers.append(block.rstrip()+"\\n")\nif {bool(enabled)!r}:\n    peers.append("[Peer]\\nPublicKey = "+pub+"\\nAllowedIPs = "+address+"\\n")\nout=head.rstrip()+"\\n"\nif peers:\n    out+="\\n"+"\\n".join(block.rstrip() for block in peers)+"\\n"\npath.write_text(out,encoding="utf-8")\n'''
    encoded = base64.b64encode(script.encode()).decode()
    await _remote_run(
        conn,
        "printf '%s' " + shlex.quote(encoded) + " | base64 -d | python3",
    )


async def _classic_wireguard(
    conn,
    credential: ProtocolCredential,
    node_id: int,
    command_type: str,
) -> str:
    item = _classic_item_for_node(credential, node_id)
    private_key, address = _wireguard_identity(item)
    public_key = await _wireguard_public_key(conn, private_key)

    if command_type == "revoke_subscription":
        await _remote_run(
            conn,
            "wg set wg-access0 peer " + shlex.quote(public_key) + " remove",
        )
        await _persist_wireguard_peer(
            conn,
            public_key=public_key,
            address=address,
            enabled=False,
        )
        return "controller_classic_revoked"

    if command_type != "restore_subscription":
        raise RuntimeError(f"unsupported command type: {command_type}")

    await _remote_run(
        conn,
        "wg set wg-access0 peer "
        + shlex.quote(public_key)
        + " allowed-ips "
        + shlex.quote(address),
    )
    await _persist_wireguard_peer(
        conn,
        public_key=public_key,
        address=address,
        enabled=True,
    )
    return "controller_classic_restored"


async def _classic_l2tp(
    conn,
    credential: ProtocolCredential,
    command_type: str,
) -> str:
    username = str(credential.username or "").strip()
    if not username or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", username):
        raise RuntimeError("stored L2TP username is unavailable")

    if command_type == "revoke_subscription":
        # Remove future authentication and terminate only PPP sessions whose
        # telemetry state file declares the exact same authenticated identity.
        script = f'''from pathlib import Path\nimport os,signal\nusername={username!r}\nchap=Path("/etc/ppp/chap-secrets")\nlines=chap.read_text(encoding="utf-8").splitlines() if chap.exists() else []\nout=[]\nfor line in lines:\n    fields=line.split()\n    if fields and fields[0]==username:\n        continue\n    out.append(line)\nchap.write_text("\\n".join(out).rstrip()+"\\n",encoding="utf-8")\nos.chmod(chap,0o600)\nstate=Path("/run/twinpanel/l2tp-sessions")\nif state.is_dir():\n    for path in state.glob("ppp*"):\n        values={{}}\n        try:\n            for raw in path.read_text(encoding="utf-8").splitlines():\n                if "=" in raw:\n                    k,v=raw.split("=",1); values[k.strip()]=v.strip()\n            if values.get("identity")!=username:\n                continue\n            pid=int(values.get("pppd_pid") or "0")\n            if pid>1:\n                try: os.kill(pid,signal.SIGTERM)\n                except ProcessLookupError: pass\n        except Exception:\n            continue\n'''
        encoded = base64.b64encode(script.encode()).decode()
        await _remote_run(
            conn,
            "printf '%s' " + shlex.quote(encoded) + " | base64 -d | python3",
        )
        return "controller_classic_revoked"

    if command_type != "restore_subscription":
        raise RuntimeError(f"unsupported command type: {command_type}")

    password = _decoded_password(credential)
    line = f"{username} * {password} *\n"
    line_b64 = base64.b64encode(line.encode()).decode()
    await _remote_run(
        conn,
        "grep -v '^"
        + re.escape(username)
        + "[[:space:]]' /etc/ppp/chap-secrets > /tmp/tpchap-enforce.$$ || true; "
        + "printf '%s' "
        + shlex.quote(line_b64)
        + " | base64 -d >> /tmp/tpchap-enforce.$$; "
        + "cat /tmp/tpchap-enforce.$$ > /etc/ppp/chap-secrets; "
        + "rm -f /tmp/tpchap-enforce.$$; chmod 600 /etc/ppp/chap-secrets",
    )
    return "controller_classic_restored"


def _stored_v2ray_uuid(credential: ProtocolCredential, node_id: int) -> str:
    item = _classic_item_for_node(credential, node_id)
    client_id = str(item.get("uuid") or "").strip()
    if not client_id:
        uri = str(item.get("uri") or "")
        match = re.match(r"^vless://([^@]+)@", uri)
        client_id = str(match.group(1) if match else "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", client_id):
        raise RuntimeError("stored V2Ray UUID is unavailable")
    return client_id


async def _classic_v2ray(
    conn,
    credential: ProtocolCredential,
    subscription_id: int,
    node_id: int,
    command_type: str,
) -> str:
    email = f"mv-{int(subscription_id)}@twinpanel"
    client_id = _stored_v2ray_uuid(credential, node_id)
    restore = command_type == "restore_subscription"
    if command_type not in {"revoke_subscription", "restore_subscription"}:
        raise RuntimeError(f"unsupported command type: {command_type}")

    script = f'''import json\np="/usr/local/etc/xray/config.json"\nd=json.load(open(p,encoding="utf-8"))\nemail={email!r}\nclient_id={client_id!r}\nfound=False\nfor inbound in d.get("inbounds",[]):\n    if not isinstance(inbound,dict) or inbound.get("protocol")!="vless":\n        continue\n    clients=inbound.setdefault("settings",{{}}).setdefault("clients",[])\n    clients[:]=[c for c in clients if not isinstance(c,dict) or c.get("email")!=email]\n    if {restore!r}:\n        clients.append({{"id":client_id,"email":email}})\n    found=True\n    break\nif not found:\n    raise SystemExit("vless inbound unavailable")\nwith open(p,"w",encoding="utf-8") as f:\n    json.dump(d,f,ensure_ascii=False,indent=2); f.write("\\n")\n'''
    encoded = base64.b64encode(script.encode()).decode()
    await _remote_run(
        conn,
        "printf '%s' "
        + shlex.quote(encoded)
        + " | base64 -d | python3 && systemctl restart xray",
    )
    return "controller_classic_restored" if restore else "controller_classic_revoked"


async def _execute_classic_command(
    *,
    db,
    conn,
    credential: ProtocolCredential,
    protocol: str,
    subscription_id: int,
    node_id: int,
    command_type: str,
) -> str:
    source_protocol = CLASSIC_SOURCE_PROTOCOL.get(protocol)
    if source_protocol is None or source_protocol != str(credential.protocol).lower():
        raise RuntimeError("classic credential protocol mismatch")

    if command_type == "restore_subscription" and not bool(credential.is_active):
        raise RuntimeError("active protocol credential is unavailable")

    if protocol == "openconnect":
        return await _classic_cisco(conn, credential, command_type)
    if protocol == "openvpn":
        return await _classic_openvpn(
            conn,
            db,
            subscription_id,
            node_id,
            command_type,
        )
    if protocol == "wireguard":
        return await _classic_wireguard(conn, credential, node_id, command_type)
    if protocol == "l2tp":
        return await _classic_l2tp(conn, credential, command_type)
    if protocol == "xray":
        return await _classic_v2ray(
            conn,
            credential,
            subscription_id,
            node_id,
            command_type,
        )
    raise RuntimeError(f"unsupported classic protocol: {protocol}")


async def _execute_command(command: dict[str, Any]) -> None:
    command_id = str(command["command_id"])
    protocol = str(command["protocol"])
    subscription_id = int(command["subscription_id"])
    node_id = int(command["node_id"])
    command_type = str(command["command_type"])

    db = SessionLocal()
    conn = None
    error: Exception | None = None
    result_code = "controller_account_applied"
    try:
        if subscription_id <= 0:
            raise RuntimeError("subscription_id is missing")

        node = db.get(Node, node_id)
        if node is None or getattr(node, "retired_at", None) is not None:
            raise RuntimeError("exit node is unavailable")

        source_protocol = CLASSIC_SOURCE_PROTOCOL.get(protocol, protocol)
        credential = (
            db.query(ProtocolCredential)
            .filter(
                ProtocolCredential.subscription_id == subscription_id,
                ProtocolCredential.protocol == source_protocol,
            )
            .first()
        )
        if credential is None:
            raise RuntimeError("protocol credential is unavailable")

        from ..routers.provision import ssh_connect_saved

        conn = await ssh_connect_saved(node, db)

        if protocol in CONTROLLER_MODERN_PROTOCOLS:
            if not credential.secret_encrypted:
                raise RuntimeError("protocol credential is unavailable")
            secret = _decode_modern_secret(protocol, credential)

            if protocol in SINGBOX_MODERN_PROTOCOLS:
                from ..singbox_subscription_accounts import apply_account, remove_account

                if command_type == "revoke_subscription":
                    await remove_account(conn, protocol, subscription_id)
                    result_code = "controller_modern_revoked"
                elif command_type == "restore_subscription":
                    if not bool(credential.is_active):
                        raise RuntimeError("active protocol credential is unavailable")
                    await apply_account(conn, node, secret)
                    result_code = "controller_modern_restored"
                else:
                    raise RuntimeError(f"unsupported command type: {command_type}")
            else:
                from ..standalone_subscription_accounts import apply_account, remove_account

                if command_type == "revoke_subscription":
                    await remove_account(conn, secret)
                    result_code = "controller_standalone_revoked"
                elif command_type == "restore_subscription":
                    if not bool(credential.is_active):
                        raise RuntimeError("active protocol credential is unavailable")
                    cfg = (
                        db.query(NodeProtocolConfig)
                        .filter(
                            NodeProtocolConfig.node_id == node_id,
                            NodeProtocolConfig.protocol == protocol,
                            NodeProtocolConfig.status == "online",
                        )
                        .first()
                    )
                    if cfg is None or not cfg.port:
                        raise RuntimeError("standalone runtime config is unavailable")
                    await apply_account(conn, node, secret, int(cfg.port))
                    result_code = "controller_standalone_restored"
                else:
                    raise RuntimeError(f"unsupported command type: {command_type}")
        else:
            result_code = await _execute_classic_command(
                db=db,
                conn=conn,
                credential=credential,
                protocol=protocol,
                subscription_id=subscription_id,
                node_id=node_id,
                command_type=command_type,
            )

    except Exception as exc:
        error = exc
    finally:
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                pass
        db.close()

    status_db = SessionLocal()
    try:
        row = (
            status_db.query(QuotaNodeCommand)
            .filter(QuotaNodeCommand.command_id == command_id)
            .with_for_update()
            .first()
        )
        if row is None:
            status_db.rollback()
            return

        now = datetime.utcnow()
        if error is None:
            row.status = "succeeded"
            row.result_code = result_code
            row.result_message = None
            row.acknowledged_at = now
        else:
            message = f"{type(error).__name__}:{str(error)[:700]}"
            if int(row.attempt_count or 0) >= _MAX_ATTEMPTS or row.expires_at <= now:
                row.status = "failed"
                row.acknowledged_at = now
                row.result_code = "controller_account_failed"
            else:
                row.status = "controller_pending"
                row.result_code = "controller_account_retry"
            row.result_message = message
        status_db.commit()
    except Exception:
        status_db.rollback()
        raise
    finally:
        status_db.close()


async def process_account_enforcement_once(*, limit: int = 20) -> int:
    processed = 0
    for _ in range(max(1, min(int(limit), 100))):
        command = _claim_next_command()
        if command is None:
            break
        await _execute_command(command)
        processed += 1
    return processed


async def account_enforcement_loop() -> None:
    """Durable controller-side worker for all 15 revoke/restore commands."""

    install_account_enforcement_hooks()
    while True:
        processed = 0
        try:
            processed = await process_account_enforcement_once(limit=20)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Account enforcement worker cycle failed")
        await asyncio.sleep(0.5 if processed else 3.0)


# Compatibility aliases keep old imports/tests harmless while runtime moves to
# the all-account V2 worker.
install_modern_enforcement_hooks = install_account_enforcement_hooks
process_modern_enforcement_once = process_account_enforcement_once
modern_enforcement_loop = account_enforcement_loop
