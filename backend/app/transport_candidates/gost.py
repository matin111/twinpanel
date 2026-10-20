from __future__ import annotations

import asyncio
import hashlib
import os
import shlex
import tarfile
import urllib.request
from pathlib import Path

from sqlalchemy.orm import Session

from .common import (
    arch,
    cache_dir,
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

# TWINPANEL_GOST_UPSTREAM_UDP_FRAME_FIX_V82
#
# GOST v3.3.0 bundles go-gost/x v0.16.0. Upstream issue go-gost/gost#911
# confirmed a datagram framing race in the shared relay UDP stream: one frame
# could be split across several writes and interleave with another endpoint,
# producing corrupted frames, unexpected EOF/reset cycles, and heavy packet
# loss. Upstream fixed the frame write in x@bc137fbd832276f2a8631c7320df3e3adaa1ddf0
# and added an end-to-end regression in
# gost@d7656ef3deafec6bf97107b20a332b938153fd54.
#
# The first official GOST artifact currently available after that fix is the
# pinned 3.3.1 nightly below. It is checksum-verified exactly like the stable
# artifact and is used only by the fail-closed gost_tun candidate. It never
# becomes SmartAuto-eligible until the common bidirectional peer ping + TCP
# egress + UDP egress canary passes.
VERSION = "3.3.1-nightly.20261017"
BASE = f"https://github.com/go-gost/gost/releases/download/v{VERSION}"
UPSTREAM_ISSUE = "go-gost/gost#911"
UPSTREAM_FIX_COMMIT = "bc137fbd832276f2a8631c7320df3e3adaa1ddf0"
UPSTREAM_E2E_COMMIT = "d7656ef3deafec6bf97107b20a332b938153fd54"
UPSTREAM_X_VERSION = "v0.19.5"
FORWARD_PORT = 8421

# TWINPANEL_GOST_PROFILE_CANARY_V81
#
# Production evidence on Tunnel #5 showed that relay+wss could establish the
# outer TCP/WebSocket session while carrying zero TUN payload bytes. Keep the
# documented WSS profile first, but fail over inside this *candidate install*
# to a plain TLS data channel before the candidate is allowed to become
# eligible for SmartAuto. A profile is accepted only after the common L3
# canary passes peer ping in both directions plus TCP and UDP egress.
PROFILE_ORDER: tuple[str, ...] = (
    "relay+wss",
    "relay+tls",
)

# TWINPANEL_GOST_RELAY_REGISTRATION_V85
#
# rc.82 production evidence narrowed the remaining failure to registration of
# the TUN peer route, not to the outer TCP/TLS/WSS path: the relay CONNECT
# reached 127.0.0.1:8421 on Exit, both TUN interfaces existed, yet both peer
# pings remained at 100% loss. The old canary then tore the profile down about
# seven seconds after start, before the configured 10s TUN keepalive could
# provide a second registration attempt.
#
# GOST relay defaults nodelay=false. In that mode the connector buffers the
# relay request together with the first UDP datagram, while the handler also
# buffers its response with the first return datagram. For TUN-over-relay the
# first UDP datagram is the address-registration frame that teaches the Exit
# TUN handler how to route return traffic. Make control-plane establishment
# explicit on *both* relay ends with nodelay=true, then allow more than one
# keepalive interval before the fail-closed L3 probe. This keeps the documented
# TUN-over-relay topology while removing first-datagram timing from canary
# eligibility.
TUN_KEEPALIVE_SECONDS = 10
REGISTRATION_SETTLE_SECONDS = 12.0


def _download(raw_arch: str) -> str:
    a = arch(raw_arch)
    root = cache_dir() / f"gost-{VERSION}-{a}"
    binary = root / "gost"
    if binary.is_file() and os.access(binary, os.X_OK):
        return str(binary)

    root.mkdir(parents=True, exist_ok=True)
    asset = f"gost_{VERSION}_linux_{a}.tar.gz"
    archive = root / asset
    sums = root / "checksums.txt"

    urllib.request.urlretrieve(f"{BASE}/{asset}", archive)
    urllib.request.urlretrieve(f"{BASE}/checksums.txt", sums)

    expected = next(
        (
            line.split()[0]
            for line in sums.read_text(errors="ignore").splitlines()
            if line.split() and line.split()[-1].lstrip("*") == asset
        ),
        None,
    )
    if not expected:
        raise RuntimeError("gost_checksum_missing")

    actual = hashlib.sha256(archive.read_bytes()).hexdigest().lower()
    if actual != expected.lower():
        raise RuntimeError("gost_checksum_mismatch")

    with tarfile.open(archive, "r:gz") as tf:
        member = next(
            (
                item
                for item in tf.getmembers()
                if item.isfile() and Path(item.name).name == "gost"
            ),
            None,
        )
        if member is None:
            raise RuntimeError("gost_binary_missing_in_archive")
        src = tf.extractfile(member)
        if src is None:
            raise RuntimeError("gost_extract_failed")
        binary.write_bytes(src.read())

    binary.chmod(0o755)
    return str(binary)


async def _wait_interface(conn, iface: str, service: str, label: str) -> None:
    for _ in range(20):
        state = await conn.run(
            f"systemctl is-active --quiet {shlex.quote(service)} && "
            f"ip link show {shlex.quote(iface)} >/dev/null 2>&1",
            check=False,
            timeout=10,
        )
        if state.exit_status == 0:
            return
        await asyncio.sleep(1)
    raise RuntimeError(f"{label}_not_ready")


async def _raw_tcp_preflight(conn, host: str, port: int) -> None:
    result = await conn.run(
        f"""python3 - <<'PY'
import socket
host={host!r}
port={int(port)}
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.settimeout(6)
try:
    s.connect((host,port))
finally:
    s.close()
PY""",
        check=False,
        timeout=12,
    )
    if result.exit_status != 0:
        text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raise RuntimeError(
            f"gost_profile_tcp_preflight_failed: {text[-2000:] or 'connect_failed'}"
        )


def _profile_label(profile: str) -> str:
    if profile == "relay+wss":
        return "WSS"
    if profile == "relay+tls":
        return "TLS"
    raise ValueError(f"unsupported_gost_profile:{profile}")


async def _reset_profile_runtime(ci, ce, rt: dict) -> None:
    """Stop only this candidate's pair before trying another profile."""

    await asyncio.gather(
        ci.run(
            f"""
set +e
systemctl stop {shlex.quote(str(rt['iran_service']))} >/dev/null 2>&1 || true
ip link del {shlex.quote(str(rt['interface']))} >/dev/null 2>&1 || true
true
""",
            check=False,
            timeout=30,
        ),
        ce.run(
            f"""
set +e
systemctl stop {shlex.quote(str(rt['exit_service']))} >/dev/null 2>&1 || true
ip link del {shlex.quote(str(rt['interface']))} >/dev/null 2>&1 || true
true
""",
            check=False,
            timeout=30,
        ),
    )


async def _install_profile_services(
    ci,
    ce,
    *,
    profile: str,
    tunnel_id: int,
    exit_public_ip: str,
    rt: dict,
) -> None:
    """Render one documented GOST relay data-channel profile on both nodes."""

    label = _profile_label(profile)
    port = int(rt["port"])

    await run(
        ce,
        f"""
set -e
cat > /etc/systemd/system/{shlex.quote(str(rt['exit_service']))} <<'EOF'
[Unit]
Description=TwinPanel GOST TUN/{label} {int(tunnel_id)} Exit
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/twinpanel-gost -L=tun://:{FORWARD_PORT}?net={rt['exit_addr']}&name={rt['interface']}&mtu=1360 -L={profile}://:{port}?bind=true&nodelay=true
Restart=always
RestartSec=2
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(str(rt['exit_service']))} >/dev/null
systemctl restart {shlex.quote(str(rt['exit_service']))}
""",
        f"gost_{label.lower()}_exit_install",
        90,
    )

    await _wait_interface(
        ce,
        str(rt["interface"]),
        str(rt["exit_service"]),
        f"gost_{label.lower()}_exit",
    )

    await _raw_tcp_preflight(ci, str(exit_public_ip), port)

    await run(
        ci,
        f"""
set -e
cat > /etc/systemd/system/{shlex.quote(str(rt['iran_service']))} <<'EOF'
[Unit]
Description=TwinPanel GOST TUN/{label} {int(tunnel_id)} Iran
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/twinpanel-gost -L=tun://:0/:{FORWARD_PORT}?net={rt['iran_addr']}&name={rt['interface']}&mtu=1360&keepalive=true&ttl={TUN_KEEPALIVE_SECONDS}s -F={profile}://{exit_public_ip}:{port}?secure=false&nodelay=true
Restart=always
RestartSec=2
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(str(rt['iran_service']))} >/dev/null
systemctl restart {shlex.quote(str(rt['iran_service']))}
""",
        f"gost_{label.lower()}_iran_install",
        90,
    )

    await _wait_interface(
        ci,
        str(rt["interface"]),
        str(rt["iran_service"]),
        f"gost_{label.lower()}_iran",
    )


async def install(tunnel_id: int, db: Session) -> dict:
    name = "gost_tun"
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    mark(db, tunnel_id, name, status="installing", meta=str(rt))

    ci = ce = None
    attempts: list[dict[str, str]] = []

    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))

        iran_arch, exit_arch = await asyncio.gather(
            run(ci, "uname -m", "iran_arch"),
            run(ce, "uname -m", "exit_arch"),
        )
        iran_binary, exit_binary = await asyncio.gather(
            asyncio.to_thread(_download, iran_arch),
            asyncio.to_thread(_download, exit_arch),
        )
        await asyncio.gather(
            copy_binary(ci, iran_binary, "/usr/local/bin/twinpanel-gost"),
            copy_binary(ce, exit_binary, "/usr/local/bin/twinpanel-gost"),
        )

        port = int(rt["port"])

        # One ownership-scoped TCP listener rule is sufficient for both WSS
        # and TLS because profiles are tried sequentially on the same port.
        await run(
            ce,
            f"""
set -e
if command -v iptables >/dev/null 2>&1; then
  iptables -C INPUT -p tcp --dport {port} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GOST-{int(tunnel_id)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p tcp --dport {port} -s {shlex.quote(str(iran.public_ip))} -m comment --comment TwinPanel-GOST-{int(tunnel_id)} -j ACCEPT
fi
""",
            "gost_firewall",
            45,
        )

        for profile in PROFILE_ORDER:
            try:
                await _reset_profile_runtime(ci, ce, rt)
                await _install_profile_services(
                    ci,
                    ce,
                    profile=profile,
                    tunnel_id=tunnel_id,
                    exit_public_ip=str(exit_node.public_ip),
                    rt=rt,
                )

                # Give the TUN registration path more than one configured
                # keepalive interval. The relay control exchange itself is
                # nodelay=true on both ends, so the first registration is no
                # longer coupled to the relay request/response framing; this
                # grace also permits one clean retry before fail-closed probe.
                await asyncio.sleep(REGISTRATION_SETTLE_SECONDS)

                health = await probe(
                    ci,
                    ce,
                    name=name,
                    tunnel_id=tunnel_id,
                    rt=rt,
                )

                attempts.append(
                    {
                        "profile": profile,
                        "result": "passed",
                    }
                )

                meta = {
                    **rt,
                    **health,
                    "version": VERSION,
                    "carrier": profile,
                    "selected_profile": profile,
                    "profile_canary": "v81",
                    "upstream_binary_fix": "v82",
                    "relay_registration_fix": "v85",
                    "registration_settle_seconds": REGISTRATION_SETTLE_SECONDS,
                    "profile_attempts": attempts,
                    "upstream_issue": UPSTREAM_ISSUE,
                    "upstream_fix_commit": UPSTREAM_FIX_COMMIT,
                    "upstream_e2e_commit": UPSTREAM_E2E_COMMIT,
                    "upstream_x_version": UPSTREAM_X_VERSION,
                }
                mark(
                    db,
                    tunnel_id,
                    name,
                    status="online",
                    latency_ms=health["latency_ms"],
                    meta=str(meta),
                )
                return {
                    "ok": True,
                    "transport": name,
                    "runtime": rt,
                    "probe": health,
                    "version": VERSION,
                    "carrier": profile,
                    "selected_profile": profile,
                    "profile_canary": "v81",
                    "upstream_binary_fix": "v82",
                    "relay_registration_fix": "v85",
                    "registration_settle_seconds": REGISTRATION_SETTLE_SECONDS,
                    "profile_attempts": attempts,
                    "upstream_issue": UPSTREAM_ISSUE,
                    "upstream_fix_commit": UPSTREAM_FIX_COMMIT,
                    "upstream_e2e_commit": UPSTREAM_E2E_COMMIT,
                    "upstream_x_version": UPSTREAM_X_VERSION,
                }

            except Exception as profile_exc:
                attempts.append(
                    {
                        "profile": profile,
                        "result": "failed",
                        "error": f"{type(profile_exc).__name__}: {profile_exc}"[-2500:],
                    }
                )

        await _reset_profile_runtime(ci, ce, rt)
        summary = "; ".join(
            f"{item['profile']}={item['error']}"
            for item in attempts
            if item.get("result") == "failed"
        )
        raise RuntimeError(
            f"gost_all_profiles_failed: {summary or 'no_profile_passed'}"
        )

    except Exception as exc:
        iran_diag = (
            await diag(ci, rt["iran_service"], rt["interface"])
            if ci
            else ""
        )
        exit_diag = (
            await diag(ce, rt["exit_service"], rt["interface"])
            if ce
            else ""
        )
        msg = (
            f"{type(exc).__name__}: {exc} | "
            f"attempts={attempts!r} | "
            f"version={VERSION} upstream={UPSTREAM_ISSUE} relay_registration=v85 | "
            f"iran={iran_diag[-2500:]} | exit={exit_diag[-2500:]}"
        )
        mark(db, tunnel_id, name, status="failed", error=msg)
        raise RuntimeError(msg) from exc

    finally:
        await close_pair(ci, ce)
