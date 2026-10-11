from __future__ import annotations

import asyncio
import base64
import ipaddress
import shlex

from .models import Node, NodeAccess
from . import ssh_relay_v2 as v2
from .ssh_relay import _host_key, _write


# ============================================================
# TWINPANEL SSH RELAY V3
#
# V11/V2 proved that ProxyJump+TunnelDevice fails on some paths and that
# split-hop is the correct fallback shape. The remaining failure was the first
# split hop never exposing the Exit SSH banner locally.
#
# The legacy relay key is source-restricted with from=<Node.public_ip>. That is
# unsafe to assume when the Iran node itself egresses through another route or
# NAT. V3 therefore discovers the *actual source address observed by the relay*
# using the dedicated relay key, immediately rewrites the key restriction to
# that observed source, installs the matching sshd forwarding policy, and only
# then starts the split-hop services.
#
# No transport is marked healthy here. V9/V10/V11 still require real
# interface/ping/UDP/egress validation before selection.
# ============================================================


async def _run(conn, command: str, *, check: bool = True, timeout: int = 120):
    result = await conn.run(command, check=False, timeout=timeout)
    if check and result.exit_status != 0:
        raise RuntimeError(
            (result.stderr or result.stdout or "remote command failed")[-4000:]
        )
    return result


def _auth_line(pub: str, *, source: str | None, exit_host: str, exit_port: int, tag: str) -> str:
    prefix = ""
    if source:
        prefix = f'from="{source}",'
    return (
        prefix
        + "no-agent-forwarding,no-X11-forwarding,no-pty,no-user-rc,"
        + f'permitopen="{exit_host}:{int(exit_port)}" '
        + f"{pub} {tag}"
    )


async def _replace_authorized_key(conn, *, line: str, tags: list[str]) -> None:
    encoded = base64.b64encode(line.encode()).decode()
    patterns = " ".join(shlex.quote(tag + "$") for tag in tags)
    await _run(
        conn,
        f"""
set -e
install -d -m 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
cp -a /root/.ssh/authorized_keys /root/.ssh/authorized_keys.bak-tp-relay-source-$(date +%Y%m%d-%H%M%S)
cp /root/.ssh/authorized_keys /root/.ssh/authorized_keys.tmp
for P in {patterns}; do
    grep -v "$P" /root/.ssh/authorized_keys.tmp > /root/.ssh/authorized_keys.next || true
    mv /root/.ssh/authorized_keys.next /root/.ssh/authorized_keys.tmp
done
printf '%s' {shlex.quote(encoded)} | base64 -d >> /root/.ssh/authorized_keys.tmp
printf '\n' >> /root/.ssh/authorized_keys.tmp
mv /root/.ssh/authorized_keys.tmp /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
""",
        timeout=35,
    )


async def _discover_relay_seen_source(tunnel, iran: Node, relay: Node, exit_node: Node, db) -> str:
    from .routers.provision import ssh_connect_saved

    relay_access = (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(relay.id))
        .first()
    )
    exit_access = (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(exit_node.id))
        .first()
    )
    if not relay_access or not exit_access:
        raise RuntimeError("source_probe_saved_access_missing")

    tid = int(tunnel.id)
    base = f"/etc/twinpanel/ssh-relay/tunnel-{tid}"
    tag = f"tp{tid}-relay-hop"
    bootstrap_tag = f"tp{tid}-relay-hop-source-probe"

    ci = cr = None
    try:
        ci = await ssh_connect_saved(iran, db)
        cr = await ssh_connect_saved(relay, db)

        await _run(
            ci,
            f"""
set -e
install -d -m 700 {shlex.quote(base)}
if [ ! -s {shlex.quote(base + '/id_ed25519')} ]; then
  ssh-keygen -q -t ed25519 -N '' -f {shlex.quote(base + '/id_ed25519')}
fi
chmod 600 {shlex.quote(base + '/id_ed25519')}
chmod 644 {shlex.quote(base + '/id_ed25519.pub')}
""",
            timeout=35,
        )

        pub = (
            await _run(
                ci,
                f"cat {shlex.quote(base + '/id_ed25519.pub')}",
                timeout=15,
            )
        ).stdout.strip()
        if not pub.startswith("ssh-ed25519 "):
            raise RuntimeError("source_probe_invalid_public_key")

        relay_host_key = await _host_key(cr)
        known = (
            f"{v2._known_host_name(str(relay.public_ip), int(relay_access.ssh_port))} "
            f"{relay_host_key}\n"
        )
        await _write(ci, base + "/source_probe_known_hosts", known, "600")

        # Bootstrap only long enough to learn the real source address seen by
        # sshd on the relay. permitopen keeps this dedicated key constrained to
        # the intended final Exit during the probe window.
        temp_line = _auth_line(
            pub,
            source=None,
            exit_host=str(exit_node.public_ip),
            exit_port=int(exit_access.ssh_port),
            tag=bootstrap_tag,
        )
        await _replace_authorized_key(
            cr,
            line=temp_line,
            tags=[tag, bootstrap_tag],
        )

        probe = await _run(
            ci,
            f"""
/usr/bin/ssh \
  -p {int(relay_access.ssh_port)} \
  -i {shlex.quote(base + '/id_ed25519')} \
  -o IdentitiesOnly=yes \
  -o BatchMode=yes \
  -o PasswordAuthentication=no \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile={shlex.quote(base + '/source_probe_known_hosts')} \
  -o ConnectTimeout=10 \
  root@{shlex.quote(str(relay.public_ip))} \
  'printf "%s\\n" "$SSH_CONNECTION"'
""",
            check=False,
            timeout=20,
        )
        if probe.exit_status != 0:
            raise RuntimeError(
                "relay_source_probe_failed: "
                + (probe.stderr or probe.stdout or "unknown")[-1800:]
            )

        fields = probe.stdout.strip().split()
        if len(fields) < 4:
            raise RuntimeError(
                f"relay_source_probe_invalid_ssh_connection:{probe.stdout.strip()!r}"
            )

        observed = fields[0]
        ipaddress.ip_address(observed)

        final_line = _auth_line(
            pub,
            source=observed,
            exit_host=str(exit_node.public_ip),
            exit_port=int(exit_access.ssh_port),
            tag=tag,
        )
        await _replace_authorized_key(
            cr,
            line=final_line,
            tags=[tag, bootstrap_tag],
        )

        # Match forwarding policy to the source actually seen by sshd rather
        # than assuming Node.public_ip is the egress address.
        await v2._install_relay_forwarding_policy(
            cr,
            tunnel_id=tid,
            iran_public_ip=observed,
        )

        print(
            f"[SSHRelayV3] HOP_SOURCE_DISCOVERED "
            f"tunnel={tid} relay_node={int(relay.id)} "
            f"observed={observed} configured={iran.public_ip}",
            flush=True,
        )
        return observed

    finally:
        for conn in (ci, cr):
            if conn:
                conn.close()
                await conn.wait_closed()


async def provision_ssh_relay_v3(tunnel, iran: Node, relay: Node, exit_node: Node, db) -> dict:
    """Primary relay + source-aware split-hop fallback.

    V61 remains the first attempt. On the known ProxyJump/TunnelDevice failure,
    discover the actual Iran->relay source address, rewrite the dedicated key
    restriction to that observed address, then retry using V2 split-hop.
    """

    await v2._prepare_relay_path(
        tunnel,
        iran,
        relay,
        exit_node,
        db,
    )

    try:
        return await v2._provision_ssh_relay_v61(
            tunnel,
            iran,
            relay,
            exit_node,
            db,
        )

    except asyncio.CancelledError:
        raise

    except Exception as primary_exc:
        primary_text = str(primary_exc)
        split_candidate = (
            "interface did not become ready" in primary_text.lower()
            or "banner" in primary_text.lower()
        )

        if not split_candidate:
            context = await v2._collect_failure_context(
                tunnel,
                iran,
                relay,
                exit_node,
                db,
            )
            raise RuntimeError(
                f"{type(primary_exc).__name__}:{primary_exc}; diagnostics={context}"
            ) from primary_exc

        print(
            f"[SSHRelayV3] SOURCE_AWARE_SPLIT_FALLBACK "
            f"tunnel={int(tunnel.id)} relay_node={int(relay.id)}",
            flush=True,
        )

        observed = None
        try:
            observed = await _discover_relay_seen_source(
                tunnel,
                iran,
                relay,
                exit_node,
                db,
            )
            result = await v2._provision_split_hop(
                tunnel,
                iran,
                relay,
                exit_node,
                db,
            )
            result["relay_seen_iran_source"] = observed
            return result

        except asyncio.CancelledError:
            raise

        except Exception as split_exc:
            context = await v2._collect_failure_context(
                tunnel,
                iran,
                relay,
                exit_node,
                db,
            )
            raise RuntimeError(
                "proxyjump_failed="
                f"{type(primary_exc).__name__}:{primary_exc}; "
                "source_aware_split_failed="
                f"{type(split_exc).__name__}:{split_exc}; "
                f"observed_source={observed}; diagnostics={context}"
            ) from split_exc
