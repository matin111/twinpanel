#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime

from app.database import SessionLocal
from app.local_core_runtime import connection_for_node, managed_protocol_nodes
from app.models import Node, NodeProtocolConfig
from app.routers.provision import (
    PROTOCOL_NAMES,
    ProtocolSettings,
    _protocol_live_health,
    _protocol_settings_from_db,
    _restart_protocol_service,
    _save_live_health,
    cmd,
    provision_protocols,
)

PROTOCOL_ORDER = ["cisco", "openvpn", "wireguard", "l2tp", "v2ray"]
ENABLE_FIELD = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}


def _managed_nodes(db):
    return managed_protocol_nodes(db)


def _select_node(db):
    nodes = _managed_nodes(db)
    print("\nManaged protocol targets")
    for row in nodes:
        target = "Local / This server" if getattr(row, "is_mother", False) else row.name
        print(f"  {row.id}) {target}  [{row.public_ip}]")
    raw = input("Node ID: ").strip()
    if not raw.isdigit():
        raise RuntimeError("INVALID_NODE_ID")
    node_id = int(raw)
    node = next((row for row in nodes if int(row.id) == node_id), None)
    if node is None:
        raise RuntimeError("NODE_NOT_FOUND")
    return node


def _select_protocol() -> str:
    print("\nProtocols")
    for index, name in enumerate(PROTOCOL_ORDER, start=1):
        print(f"  {index}) {PROTOCOL_NAMES[name]}")
    raw = input("Protocol: ").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(PROTOCOL_ORDER):
        raise RuntimeError("INVALID_PROTOCOL")
    return PROTOCOL_ORDER[int(raw) - 1]


def _select_action() -> str:
    actions = [
        ("status", "Status"),
        ("install", "Install"),
        ("repair", "Repair"),
        ("restart", "Restart"),
        ("remove", "Remove"),
    ]
    print("\nActions")
    for index, (_, title) in enumerate(actions, start=1):
        print(f"  {index}) {title}")
    raw = input("Action: ").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(actions):
        raise RuntimeError("INVALID_ACTION")
    return actions[int(raw) - 1][0]


def _settings_for(protocol: str, item: NodeProtocolConfig | None) -> ProtocolSettings:
    kwargs = {
        "install_cisco": False,
        "install_openvpn": False,
        "install_wireguard": False,
        "install_l2tp": False,
        "install_v2ray": False,
        "cisco_port": 443,
        "openvpn_port": 1194,
        "openvpn_transport": "udp",
        "wireguard_port": 51820,
        "xray_port": 8443,
    }
    if protocol == "cisco":
        kwargs["install_cisco"] = True
        if item and item.port:
            kwargs["cisco_port"] = int(item.port)
    elif protocol == "openvpn":
        kwargs["install_openvpn"] = True
        if item and item.port:
            kwargs["openvpn_port"] = int(item.port)
        if item and item.transport in {"udp", "tcp"}:
            kwargs["openvpn_transport"] = item.transport
    elif protocol == "wireguard":
        kwargs["install_wireguard"] = True
        if item and item.port:
            kwargs["wireguard_port"] = int(item.port)
    elif protocol == "l2tp":
        kwargs["install_l2tp"] = True
    elif protocol == "v2ray":
        kwargs["install_v2ray"] = True
        if item and item.port:
            kwargs["xray_port"] = int(item.port)
    else:
        raise RuntimeError("INVALID_PROTOCOL")
    return ProtocolSettings(**kwargs)


def _release_db_transaction(db) -> None:
    """Release checked-out DB connection before slow local/SSH I/O.

    SessionLocal uses expire_on_commit=False, so already-loaded Node and
    NodeProtocolConfig values remain usable after this commit. This prevents an
    idle transaction from being held while apt/systemd/network commands run.
    """
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _rollback_db(db) -> None:
    try:
        db.rollback()
    except Exception:
        pass


async def _backup_protocol(conn, protocol: str) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    base = f"/var/lib/twinpanel-protocol-backups/{stamp}-{protocol}"
    paths = {
        "cisco": ["/etc/ocserv"],
        "openvpn": ["/etc/openvpn/server/twinpanel.conf", "/etc/twinpanel/openvpn"],
        "wireguard": ["/etc/wireguard/wg-access0.conf", "/etc/wireguard/wg-access0.key"],
        "l2tp": ["/etc/ipsec.conf", "/etc/ipsec.secrets", "/etc/xl2tpd/xl2tpd.conf", "/etc/ppp/options.xl2tpd"],
        "v2ray": ["/usr/local/etc/xray/config.json", "/etc/xray/config.json"],
    }[protocol]
    quoted = " ".join(f"'{value}'" for value in paths)
    await cmd(
        conn,
        f"mkdir -p '{base}'; for p in {quoted}; do if [ -e \"$p\" ]; then cp -a --parents \"$p\" '{base}/' 2>/dev/null || true; fi; done; echo '{base}'",
        check=False,
    )
    return base


async def _ufw_delete(conn, rules: list[tuple[int, str]]) -> None:
    active = "Status: active" in await cmd(conn, "ufw status 2>/dev/null | head -1", check=False)
    if not active:
        return
    for port, proto in rules:
        await cmd(conn, f"ufw --force delete allow {int(port)}/{proto} >/dev/null 2>&1 || true", check=False)


async def _remove_runtime(conn, protocol: str, item: NodeProtocolConfig | None) -> str:
    backup = await _backup_protocol(conn, protocol)
    if protocol == "cisco":
        port = int(item.port if item and item.port else 443)
        await cmd(conn, "systemctl disable --now ocserv >/dev/null 2>&1 || true", check=False)
        await cmd(conn, "rm -f /etc/ocserv/ocserv.conf /etc/ocserv/server-cert.pem /etc/ocserv/server-key.pem /etc/ocserv/ocpasswd /etc/twinpanel/managed-identities/cisco", check=False)
        await _ufw_delete(conn, [(port, "tcp"), (port, "udp")])
    elif protocol == "openvpn":
        port = int(item.port if item and item.port else 1194)
        transport = item.transport if item and item.transport in {"udp", "tcp"} else "udp"
        await cmd(conn, "systemctl disable --now openvpn-server@twinpanel >/dev/null 2>&1 || true; systemctl disable --now openvpn@twinpanel >/dev/null 2>&1 || true", check=False)
        await cmd(conn, "rm -f /etc/openvpn/server/twinpanel.conf /etc/twinpanel/managed-identities/openvpn", check=False)
        await _ufw_delete(conn, [(port, transport)])
    elif protocol == "wireguard":
        port = int(item.port if item and item.port else 51820)
        await cmd(conn, "systemctl disable --now wg-quick@wg-access0 >/dev/null 2>&1 || true; ip link del wg-access0 >/dev/null 2>&1 || true", check=False)
        await cmd(conn, "rm -f /etc/wireguard/wg-access0.conf /etc/wireguard/wg-access0.key /etc/twinpanel/managed-identities/wireguard", check=False)
        await _ufw_delete(conn, [(port, "udp")])
    elif protocol == "l2tp":
        await cmd(conn, "systemctl disable --now xl2tpd >/dev/null 2>&1 || true; systemctl disable --now strongswan-starter >/dev/null 2>&1 || true; systemctl disable --now strongswan >/dev/null 2>&1 || true", check=False)
        await cmd(conn, "rm -f /etc/ipsec.conf /etc/ipsec.secrets /etc/xl2tpd/xl2tpd.conf /etc/ppp/options.xl2tpd", check=False)
        await _ufw_delete(conn, [(500, "udp"), (4500, "udp"), (1701, "udp")])
    elif protocol == "v2ray":
        port = int(item.port if item and item.port else 8443)
        await cmd(conn, "systemctl disable --now xray >/dev/null 2>&1 || true", check=False)
        await cmd(conn, "rm -f /usr/local/etc/xray/config.json /etc/xray/config.json", check=False)
        await _ufw_delete(conn, [(port, "tcp")])
    else:
        raise RuntimeError("INVALID_PROTOCOL")
    return backup


async def _run(db, node: Node, protocol: str, action: str) -> dict:
    stored = _protocol_settings_from_db(db, node.id)
    item = stored.get(protocol)

    # The settings query above starts a SQLAlchemy transaction. Never keep that
    # transaction checked out while apt/systemd/SSH commands can run for
    # minutes. SessionLocal is expire_on_commit=False, so item/node remain safe
    # to read after releasing the connection back to the pool.
    _release_db_transaction(db)

    conn = None
    try:
        conn = await connection_for_node(node, db)

        # Remote targets read NodeAccess before connecting. Release that short
        # lookup transaction before protocol commands begin as well.
        _release_db_transaction(db)

        if action == "status":
            result = await _protocol_live_health(conn, protocol, item)
            _save_live_health(db, node, protocol, result)
            db.commit()
            return {"ok": bool(result.get("ok")), "action": action, "protocol": protocol, "target": "local" if node.is_mother else "remote", "result": result}

        if action == "restart":
            service = await _restart_protocol_service(conn, protocol, item)
            await asyncio.sleep(1)
            result = await _protocol_live_health(conn, protocol, item)
            _save_live_health(db, node, protocol, result)
            db.commit()
            return {"ok": bool(result.get("ok")), "action": action, "protocol": protocol, "target": "local" if node.is_mother else "remote", "service": service, "result": result}

        if action in {"install", "repair"}:
            if action == "install":
                current = await _protocol_live_health(conn, protocol, item)
                if current.get("ok"):
                    return {"ok": True, "action": action, "protocol": protocol, "target": "local" if node.is_mother else "remote", "skipped": True, "reason": "already_healthy", "result": current}

            settings = _settings_for(protocol, item)
            try:
                results, failed, secrets_out = await provision_protocols(
                    conn,
                    settings,
                    db,
                    node,
                    repair=(action == "repair"),
                )
            except Exception:
                # A failed flush/commit leaves a SQLAlchemy Session unusable
                # until rollback. Clean it here before returning control to the
                # menu instead of leaking PendingRollbackError.
                _rollback_db(db)
                raise

            fresh_item = _protocol_settings_from_db(db, node.id).get(protocol)
            _release_db_transaction(db)
            health = await _protocol_live_health(conn, protocol, fresh_item)
            _save_live_health(db, node, protocol, health)
            db.commit()
            return {
                "ok": bool(health.get("ok")) and protocol not in failed,
                "action": action,
                "protocol": protocol,
                "target": "local" if node.is_mother else "remote",
                "provision": results.get(protocol),
                "health": health,
                "one_time_secrets": secrets_out,
            }

        if action == "remove":
            backup = await _remove_runtime(conn, protocol, item)
            setattr(node, ENABLE_FIELD[protocol], False)
            if item is None:
                item = NodeProtocolConfig(node_id=node.id, protocol=protocol)
                db.add(item)
            item.status = "disabled"
            item.last_error = None
            item.checked_at = datetime.utcnow()
            db.commit()
            return {"ok": True, "action": action, "protocol": protocol, "target": "local" if node.is_mother else "remote", "backup": backup}

        raise RuntimeError("INVALID_ACTION")
    except Exception:
        _rollback_db(db)
        raise
    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()


def main() -> int:
    db = SessionLocal()
    try:
        protocol = _select_protocol()
        node = _select_node(db)
        action = _select_action()
        if action == "remove":
            expected = f"REMOVE {protocol}"
            typed = input(f"Type '{expected}' to confirm: ").strip()
            if typed != expected:
                print("Cancelled")
                return 0
        target = "Local / This server" if node.is_mother else node.name
        print(f"\nTarget: {target} ({node.public_ip})")
        print(f"Protocol: {PROTOCOL_NAMES[protocol]}")
        print(f"Action: {action}\n")
        result = asyncio.run(_run(db, node, protocol, action))
        print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
        return 0 if result.get("ok") else 1
    except KeyboardInterrupt:
        _rollback_db(db)
        print("\nCancelled")
        return 130
    except Exception as exc:
        _rollback_db(db)
        print(f"ERROR={exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
