from __future__ import annotations

import ast
import asyncio
import hashlib
import ipaddress
import json
import re
import shlex
from pathlib import Path

from sqlalchemy.orm import Session

from .common import (
    close_pair,
    connect_pair,
    copy_binary,
    diag,
    mark,
    prerequisites,
    probe,
    run,
    runtime,
    tunnel_nodes,
)


# ============================================================
# TWINPANEL SPOOF + WIREGUARD L3 V202
#
# Spoof Tunnel is an outer packet carrier, not a TUN device. TwinPanel keeps a
# real WireGuard /30 as the authoritative L3 dataplane and feeds WireGuard's
# UDP endpoint through the pinned Spoof Tunnel core on both nodes:
#
#   Iran WG -> local Spoof relay -> spoofed outer packet -> Exit Spoof relay
#           -> Exit WG -> real /30 peer L3
#
# Reverse traffic follows the symmetric relay path. XDP stays disabled in V202
# so the first production qualification depends only on the upstream raw-socket
# path and does not add kernel/NIC-driver requirements.
#
# Upstream: https://github.com/ParsaKSH/spoof-tunnel
# License : Apache-2.0
# Pinned release: v3.1.0-beta.0 / upstream source ba29f0c8...
# ============================================================

NAME = "spoof_wg"
MTU = 1280
REMOTE_BINARY = "/opt/twinpanel/transport/spoof-tunnel"
ARTIFACT_NAME = "spoof-tunnel-linux-x86_64"
UPSTREAM_VERSION = "v3.1.0-beta.0"
UPSTREAM_SOURCE_SHA = "ba29f0c8e22da5a905a74a8137e01a22f0443e60"
UPSTREAM_ARTIFACT_SHA256 = "4ba5597568607e864fb6d5ba4f13bac91a50456da5696d99463d6375ce2a3697"
SEND_TRANSPORT = "tcp"
RECV_TRANSPORT = "udp"
SPOOF_SOURCE_PORT = 443


def _artifact() -> tuple[Path, str]:
    backend_dir = Path(__file__).resolve().parents[2]
    artifact = backend_dir / "artifacts" / ARTIFACT_NAME
    sidecar = backend_dir / "artifacts" / f"{ARTIFACT_NAME}.sha256"

    if not artifact.is_file():
        raise RuntimeError(f"spoof_wg_artifact_missing:{artifact}")
    if not sidecar.is_file():
        raise RuntimeError(f"spoof_wg_checksum_missing:{sidecar}")

    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    if expected != UPSTREAM_ARTIFACT_SHA256:
        raise RuntimeError(
            "spoof_wg_checksum_contract_mismatch:"
            f"expected={UPSTREAM_ARTIFACT_SHA256}:sidecar={expected}"
        )

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError(
            "spoof_wg_artifact_checksum_mismatch:"
            f"expected={expected}:actual={digest}"
        )

    return artifact, expected


def _meta_dict(raw: str | None) -> dict:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    try:
        value = ast.literal_eval(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {}


def _valid_ipv4(value: object, label: str) -> str:
    text = str(value or "").strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError as exc:
        raise ValueError(f"{label}_invalid_ipv4") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise ValueError(f"{label}_ipv4_required")
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise ValueError(f"{label}_unsupported_ipv4")
    return str(address)


def validate_configuration(payload: dict | None) -> dict:
    source = payload if isinstance(payload, dict) else {}
    return {
        "iran_spoof_ip": _valid_ipv4(source.get("iran_spoof_ip"), "iran_spoof_ip"),
        "exit_spoof_ip": _valid_ipv4(source.get("exit_spoof_ip"), "exit_spoof_ip"),
        "send_transport": SEND_TRANSPORT,
        "recv_transport": RECV_TRANSPORT,
        "xdp": False,
    }


def configuration_from_text(raw: str | None) -> dict | None:
    meta = _meta_dict(raw)
    cfg = meta.get("spoof_config")
    if not isinstance(cfg, dict):
        return None
    try:
        return validate_configuration(cfg)
    except ValueError:
        return None


def configuration_for_view(raw: str | None) -> dict:
    meta = _meta_dict(raw)
    cfg = meta.get("spoof_config")
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "iran_spoof_ip": str(cfg.get("iran_spoof_ip") or ""),
        "exit_spoof_ip": str(cfg.get("exit_spoof_ip") or ""),
        "send_transport": SEND_TRANSPORT,
        "recv_transport": RECV_TRANSPORT,
        "xdp": False,
        "configured": configuration_from_text(raw) is not None,
    }


def merge_configuration(raw: str | None, configuration: dict) -> str:
    cfg = validate_configuration(configuration)
    meta = _meta_dict(raw)
    meta["spoof_config"] = cfg
    return json.dumps(meta, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _ports(tunnel_id: int) -> dict[str, int]:
    slot = int(tunnel_id) % 500
    return {
        "iran_local_relay_port": 34000 + slot,
        "exit_raw_receive_port": 35000 + slot,
        "iran_raw_receive_port": 36000 + slot,
        "exit_wireguard_port": 37000 + slot,
        "spoof_source_port": SPOOF_SOURCE_PORT,
    }


def _key_path(tunnel_id: int, role: str) -> str:
    return f"/etc/twinpanel/spoof-wg/tunnel-{int(tunnel_id)}-{role}.key"


def _helper_path(tunnel_id: int, role: str) -> str:
    return f"/usr/local/sbin/twinpanel-spoof-wg-{int(tunnel_id)}-{role}"


async def _ensure_wireguard(conn) -> None:
    check = await conn.run(
        "command -v wg >/dev/null 2>&1 && command -v ip >/dev/null 2>&1",
        check=False,
        timeout=15,
    )
    if check.exit_status != 0:
        await run(
            conn,
            "export DEBIAN_FRONTEND=noninteractive; "
            "apt-get update -qq; apt-get install -y -qq wireguard-tools",
            "spoof_wg_wireguard_tools",
            300,
        )
    await conn.run("modprobe wireguard >/dev/null 2>&1 || true", check=False, timeout=15)


async def _keypair(conn, path: str) -> tuple[str, str]:
    out = await run(
        conn,
        f"""
set -e
install -d -m 0700 /etc/twinpanel/spoof-wg
if [ ! -s {shlex.quote(path)} ]; then
  umask 077
  wg genkey > {shlex.quote(path)}
fi
chmod 0600 {shlex.quote(path)}
P="$(cat {shlex.quote(path)})"
printf '%s\n%s\n' "$P" "$(printf '%s' "$P" | wg pubkey)"
""",
        "spoof_wg_keypair",
        30,
    )
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError("spoof_wg_key_generation_failed")
    return lines[-2], lines[-1]


async def _remove_owned_firewall(
    ci,
    ce,
    *,
    tunnel_id: int,
    rt: dict,
    cfg: dict | None,
) -> None:
    if not cfg:
        return
    ports = _ports(tunnel_id)
    iran_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-IRAN"
    exit_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-EXIT"
    l3_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-L3"

    await asyncio.gather(
        ci.run(
            f"""
set +e
if command -v iptables >/dev/null 2>&1; then
  while iptables -C INPUT -p udp --dport {ports['iran_raw_receive_port']} -s {shlex.quote(cfg['exit_spoof_ip'])} -m comment --comment {shlex.quote(iran_comment)} -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -p udp --dport {ports['iran_raw_receive_port']} -s {shlex.quote(cfg['exit_spoof_ip'])} -m comment --comment {shlex.quote(iran_comment)} -j ACCEPT || break
  done
  while iptables -C INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT || break
  done
fi
true
""",
            check=False,
        ),
        ce.run(
            f"""
set +e
if command -v iptables >/dev/null 2>&1; then
  while iptables -C INPUT -p tcp --dport {ports['exit_raw_receive_port']} -s {shlex.quote(cfg['iran_spoof_ip'])} -m comment --comment {shlex.quote(exit_comment)} -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -p tcp --dport {ports['exit_raw_receive_port']} -s {shlex.quote(cfg['iran_spoof_ip'])} -m comment --comment {shlex.quote(exit_comment)} -j ACCEPT || break
  done
  while iptables -C INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT || break
  done
  while iptables -C FORWARD -i {shlex.quote(rt['interface'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null; do
    iptables -D FORWARD -i {shlex.quote(rt['interface'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT || break
  done
  while iptables -C FORWARD -o {shlex.quote(rt['interface'])} -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null; do
    iptables -D FORWARD -o {shlex.quote(rt['interface'])} -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT || break
  done
fi
true
""",
            check=False,
        ),
    )


async def _reset_pair(ci, ce, rt: dict, cfg: dict | None = None) -> None:
    tunnel_id = int(rt["tunnel_id"])
    await _remove_owned_firewall(
        ci,
        ce,
        tunnel_id=tunnel_id,
        rt=rt,
        cfg=cfg,
    )

    await asyncio.gather(
        ci.run(
            f"""
set +e
systemctl disable --now {shlex.quote(rt['iran_service'])} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{shlex.quote(rt['iran_service'])}
rm -f {shlex.quote(_helper_path(tunnel_id, 'iran'))}
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
systemctl daemon-reload >/dev/null 2>&1 || true
true
""",
            check=False,
        ),
        ce.run(
            f"""
set +e
systemctl disable --now {shlex.quote(rt['exit_service'])} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{shlex.quote(rt['exit_service'])}
rm -f {shlex.quote(_helper_path(tunnel_id, 'exit'))}
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
systemctl daemon-reload >/dev/null 2>&1 || true
true
""",
            check=False,
        ),
    )


async def _install_firewall(ci, ce, *, tunnel_id: int, rt: dict, cfg: dict) -> None:
    ports = _ports(tunnel_id)
    iran_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-IRAN"
    exit_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-EXIT"
    l3_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-L3"

    await asyncio.gather(
        run(
            ci,
            f"""
set -e
if command -v iptables >/dev/null 2>&1; then
  iptables -C INPUT -p udp --dport {ports['iran_raw_receive_port']} -s {shlex.quote(cfg['exit_spoof_ip'])} -m comment --comment {shlex.quote(iran_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p udp --dport {ports['iran_raw_receive_port']} -s {shlex.quote(cfg['exit_spoof_ip'])} -m comment --comment {shlex.quote(iran_comment)} -j ACCEPT
  iptables -C INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT
fi
""",
            "spoof_wg_iran_firewall",
            30,
        ),
        run(
            ce,
            f"""
set -e
if command -v iptables >/dev/null 2>&1; then
  iptables -C INPUT -p tcp --dport {ports['exit_raw_receive_port']} -s {shlex.quote(cfg['iran_spoof_ip'])} -m comment --comment {shlex.quote(exit_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p tcp --dport {ports['exit_raw_receive_port']} -s {shlex.quote(cfg['iran_spoof_ip'])} -m comment --comment {shlex.quote(exit_comment)} -j ACCEPT
  iptables -C INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT
  iptables -C FORWARD -i {shlex.quote(rt['interface'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I FORWARD -i {shlex.quote(rt['interface'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT
  iptables -C FORWARD -o {shlex.quote(rt['interface'])} -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I FORWARD -o {shlex.quote(rt['interface'])} -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT
fi
""",
            "spoof_wg_exit_firewall",
            30,
        ),
    )


async def _write_peer_runtime(
    conn,
    *,
    role: str,
    tunnel_id: int,
    rt: dict,
    private_key_path: str,
    peer_public_key: str,
    cfg: dict,
    iran_public: str,
    exit_public: str,
) -> None:
    ports = _ports(tunnel_id)
    helper = _helper_path(tunnel_id, role)
    iface = rt["interface"]

    if role == "iran":
        local_addr = rt["iran_addr"]
        peer_ip = rt["exit_ip"]
        wg_setup = (
            f"wg set \"$IFACE\" private-key \"$KEY\" listen-port 0 "
            f"peer {shlex.quote(peer_public_key)} "
            f"allowed-ips {shlex.quote(peer_ip + '/32')} "
            f"endpoint 127.0.0.1:{ports['iran_local_relay_port']} "
            "persistent-keepalive 5"
        )
        exec_start = (
            f"{REMOTE_BINARY} local "
            f"--listen 127.0.0.1:{ports['iran_local_relay_port']} "
            f"--remote {shlex.quote(exit_public)} "
            f"--remote-port {ports['exit_raw_receive_port']} "
            f"--recv-port {ports['iran_raw_receive_port']} "
            f"--spoof-ip {shlex.quote(cfg['iran_spoof_ip'])} "
            f"--spoof-port {ports['spoof_source_port']} "
            f"--peer-spoof-ip {shlex.quote(cfg['exit_spoof_ip'])} "
            f"--send-transport {SEND_TRANSPORT} "
            f"--recv-transport {RECV_TRANSPORT}"
        )
        service = rt["iran_service"]
    else:
        local_addr = rt["exit_addr"]
        peer_ip = rt["iran_ip"]
        wg_setup = (
            f"wg set \"$IFACE\" private-key \"$KEY\" "
            f"listen-port {ports['exit_wireguard_port']} "
            f"peer {shlex.quote(peer_public_key)} "
            f"allowed-ips {shlex.quote(peer_ip + '/32')}"
        )
        exec_start = (
            f"{REMOTE_BINARY} remote "
            f"--listen-port {ports['exit_raw_receive_port']} "
            f"--forward 127.0.0.1:{ports['exit_wireguard_port']} "
            f"--client-ip {shlex.quote(iran_public)} "
            f"--client-port {ports['iran_raw_receive_port']} "
            f"--spoof-ip {shlex.quote(cfg['exit_spoof_ip'])} "
            f"--spoof-port {ports['spoof_source_port']} "
            f"--peer-spoof-ip {shlex.quote(cfg['iran_spoof_ip'])} "
            f"--send-transport {RECV_TRANSPORT} "
            f"--recv-transport {SEND_TRANSPORT}"
        )
        service = rt["exit_service"]

    helper_text = f"""#!/bin/bash
set -Eeuo pipefail
ACTION="${{1:-up}}"
IFACE={shlex.quote(iface)}
KEY={shlex.quote(private_key_path)}

if [ "$ACTION" = "down" ]; then
  ip link del "$IFACE" >/dev/null 2>&1 || true
  exit 0
fi

ip link del "$IFACE" >/dev/null 2>&1 || true
ip link add "$IFACE" type wireguard
{wg_setup}
ip addr replace {shlex.quote(local_addr)} dev "$IFACE"
ip link set dev "$IFACE" mtu {MTU} up
sysctl -w "net.ipv4.conf.$IFACE.rp_filter=2" >/dev/null 2>&1 || true
"""

    unit = f"""[Unit]
Description=TwinPanel Spoof WG {int(tunnel_id)} {role}
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
ExecStartPre={helper} up
ExecStart={exec_start}
ExecStopPost={helper} down
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    await run(
        conn,
        f"""
set -e
install -d -m 0755 /opt/twinpanel/transport
cat > {shlex.quote(helper)} <<'EOF'
{helper_text}EOF
chmod 0755 {shlex.quote(helper)}
cat > /etc/systemd/system/{shlex.quote(service)} <<'EOF'
{unit}EOF
systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
""",
        f"spoof_wg_{role}_install",
        60,
    )


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = dict(runtime(NAME, tunnel_id))
    rt["tunnel_id"] = int(tunnel_id)

    row = (
        db.query(__import__("app.models", fromlist=["TunnelTransport"]).TunnelTransport)
        .filter_by(tunnel_id=int(tunnel_id), transport=NAME)
        .first()
    )
    cfg = configuration_from_text(getattr(row, "config_text", None))
    if cfg is None:
        raise RuntimeError("spoof_wg_configuration_required")

    artifact_path, artifact_sha = _artifact()
    meta = {
        **rt,
        "generation": 202,
        "carrier_class": "spoof-mutual-ip-wireguard-l3",
        "depends_on": "wireguard",
        "mtu": MTU,
        "ports": _ports(tunnel_id),
        "spoof_config": cfg,
        "upstream_version": UPSTREAM_VERSION,
        "upstream_source_sha": UPSTREAM_SOURCE_SHA,
        "artifact_sha256": artifact_sha,
        "xdp": False,
    }
    mark(db, tunnel_id, NAME, status="installing", meta=json.dumps(meta, separators=(",", ":"), sort_keys=True))

    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))
        await asyncio.gather(_ensure_wireguard(ci), _ensure_wireguard(ce))
        await asyncio.gather(
            copy_binary(ci, str(artifact_path), REMOTE_BINARY),
            copy_binary(ce, str(artifact_path), REMOTE_BINARY),
        )

        iran_key_path = _key_path(tunnel_id, "iran")
        exit_key_path = _key_path(tunnel_id, "exit")
        (iran_private, iran_public_key), (exit_private, exit_public_key) = await asyncio.gather(
            _keypair(ci, iran_key_path),
            _keypair(ce, exit_key_path),
        )
        _ = iran_private, exit_private

        await _reset_pair(ci, ce, rt, cfg)

        # Exit must be able to receive the first spoofed WireGuard handshake
        # before the Iran relay starts emitting it.
        await _write_peer_runtime(
            ce,
            role="exit",
            tunnel_id=int(tunnel_id),
            rt=rt,
            private_key_path=exit_key_path,
            peer_public_key=iran_public_key,
            cfg=cfg,
            iran_public=str(iran.public_ip),
            exit_public=str(exit_node.public_ip),
        )
        await asyncio.sleep(1.0)
        await _write_peer_runtime(
            ci,
            role="iran",
            tunnel_id=int(tunnel_id),
            rt=rt,
            private_key_path=iran_key_path,
            peer_public_key=exit_public_key,
            cfg=cfg,
            iran_public=str(iran.public_ip),
            exit_public=str(exit_node.public_ip),
        )
        await _install_firewall(
            ci,
            ce,
            tunnel_id=int(tunnel_id),
            rt=rt,
            cfg=cfg,
        )

        await asyncio.sleep(5.0)
        health = await probe(
            ci,
            ce,
            name=NAME,
            tunnel_id=int(tunnel_id),
            rt=rt,
        )

        final_meta = {
            **meta,
            **health,
            "wireguard": True,
            "qualification": "full-shared-l3-probe",
        }
        mark(
            db,
            tunnel_id,
            NAME,
            status="online",
            latency_ms=health["latency_ms"],
            meta=json.dumps(final_meta, separators=(",", ":"), sort_keys=True),
        )
        return {
            "ok": True,
            "transport": NAME,
            "runtime": rt,
            "probe": health,
            "upstream_version": UPSTREAM_VERSION,
            "xdp": False,
        }

    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        message = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={a[-2200:]} | exit={b[-2200:]}"
        )
        if ci is not None and ce is not None:
            try:
                await _reset_pair(ci, ce, rt, cfg)
            except Exception:
                pass
        mark(db, tunnel_id, NAME, status="failed", error=message)
        raise RuntimeError(message) from exc

    finally:
        await close_pair(ci, ce)
