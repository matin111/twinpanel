from __future__ import annotations

import asyncio
import json
import re
import shlex
from collections import defaultdict

from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport
from .routers.provision import ssh_connect_saved


# ============================================================
# TWINPANEL MULTI-TUNNEL ORPHAN RECONCILER V1
#
# Safety model:
#   * the database is the authority for logical tunnel identity;
#   * a runtime is eligible for cleanup ONLY when its tunnel id is absent
#     from the entire tunnels table;
#   * current DB tunnel ids are never touched, regardless of transport state;
#   * only TwinPanel-namespaced runtime resources are considered;
#   * an orphan must be observed in multiple reconcile passes before cleanup;
#   * retired nodes are never contacted;
#   * only nodes participating in a current tunnel, or a current SSH relay,
#     are scanned. Historical duplicate nodes are therefore excluded.
# ============================================================

RECONCILE_INTERVAL_SECONDS = 600
RECONCILE_INITIAL_DELAY_SECONDS = 75
ORPHAN_CONFIRM_CYCLES = 2

_confirmations: dict[tuple[int, int], int] = defaultdict(int)


_UNIT_PATTERNS = (
    re.compile(r"^twinpanel-mtunnel-(\d+)\.service$"),
    re.compile(r"^twinpanel-backhaul-(\d+)\.service$"),
    re.compile(r"^twinpanel-2027-(?:kcp|tcp|quic|arq)(\d+)\.service$"),
    re.compile(r"^twinpanel-(?:gost_tun|kernel_gre)-(\d+)-iran\.service$"),
    re.compile(r"^twinpanel-(?:mother-egress|backhaul-egress)-(\d+)-iran\.service$"),
    re.compile(r"^twinpanel-backhaul-route-guardian-(\d+)\.service$"),
    re.compile(r"^tp(\d+)-(?:ssh|exit-tun|iran-tun)\.service$"),
    re.compile(r"^tp(\d+)-(?:relay-ssh|relay-if|relay-exit-if|relay-hop|relay-tls)\.service$"),
    re.compile(r"^tp(\d+)-(?:tls-client|stunnel-client)\.service$"),
)


async def _run(conn, command: str, *, timeout: int = 90):
    result = await conn.run(
        command,
        check=False,
        timeout=timeout,
    )

    if result.exit_status != 0:
        text = (
            result.stderr
            or result.stdout
            or f"exit={result.exit_status}"
        )
        raise RuntimeError(str(text)[-2500:])

    return result


def _desired_tunnel_ids(db) -> set[int]:
    return {
        int(row[0])
        for row in db.query(Tunnel.id).all()
    }


def _current_node_ids(db) -> set[int]:
    ids: set[int] = set()

    for iran_id, exit_id in db.query(
        Tunnel.iran_node_id,
        Tunnel.exit_node_id,
    ).all():
        ids.add(int(iran_id))
        ids.add(int(exit_id))

    relay_rows = (
        db.query(TunnelTransport)
        .filter(TunnelTransport.transport == "ssh_relay")
        .all()
    )

    for row in relay_rows:
        if not row.config_text:
            continue

        try:
            cfg = json.loads(row.config_text)
        except Exception:
            continue

        if not isinstance(cfg, dict):
            continue

        try:
            relay_node_id = int(cfg.get("relay_node_id") or 0)
        except Exception:
            relay_node_id = 0

        if relay_node_id > 0:
            ids.add(relay_node_id)

    return ids


def _current_nodes(db) -> list[Node]:
    ids = _current_node_ids(db)

    if not ids:
        return []

    return (
        db.query(Node)
        .filter(
            Node.id.in_(sorted(ids)),
            Node.retired_at.is_(None),
        )
        .order_by(Node.id.asc())
        .all()
    )


def _extract_runtime_ids(text: str) -> set[int]:
    ids: set[int] = set()

    for raw in str(text or "").splitlines():
        value = raw.strip()
        if not value:
            continue

        # Explicit inventory records emitted by the remote script.
        if value.startswith("ID="):
            try:
                ids.add(int(value.split("=", 1)[1]))
            except Exception:
                pass
            continue

        # Defensive parser for unit names if inventory output changes later.
        base = value.rsplit("/", 1)[-1]
        for pattern in _UNIT_PATTERNS:
            match = pattern.match(base)
            if match:
                ids.add(int(match.group(1)))
                break

    return ids


async def _inventory_node(node: Node, db) -> set[int]:
    conn = await ssh_connect_saved(node, db)

    try:
        result = await _run(
            conn,
            r"""
python3 - <<'PY'
from pathlib import Path
import re

ids=set()

unit_patterns=(
    re.compile(r'^twinpanel-mtunnel-(\d+)\.service$'),
    re.compile(r'^twinpanel-backhaul-(\d+)\.service$'),
    re.compile(r'^twinpanel-2027-(?:kcp|tcp|quic|arq)(\d+)\.service$'),
    re.compile(r'^twinpanel-(?:gost_tun|kernel_gre)-(\d+)-iran\.service$'),
    re.compile(r'^twinpanel-(?:mother-egress|backhaul-egress)-(\d+)-iran\.service$'),
    re.compile(r'^twinpanel-backhaul-route-guardian-(\d+)\.service$'),
    re.compile(r'^tp(\d+)-(?:ssh|exit-tun|iran-tun)\.service$'),
    re.compile(r'^tp(\d+)-(?:relay-ssh|relay-if|relay-exit-if|relay-hop|relay-tls)\.service$'),
    re.compile(r'^tp(\d+)-(?:tls-client|stunnel-client)\.service$'),
)

root=Path('/etc/systemd/system')
if root.exists():
    for path in root.iterdir():
        name=path.name
        for pattern in unit_patterns:
            m=pattern.match(name)
            if m:
                ids.add(int(m.group(1)))
                break

for directory, pattern in (
    ('/etc/twinpanel/mtunnel', re.compile(r'^tunnel-(\d+)\.json$')),
    ('/etc/twinpanel/backhaul', re.compile(r'^tunnel-(\d+)\.toml$')),
    ('/etc/twinpanel/ssh-relay', re.compile(r'^tunnel-(\d+)$')),
):
    p=Path(directory)
    if not p.exists():
        continue
    for item in p.iterdir():
        m=pattern.match(item.name)
        if m:
            ids.add(int(m.group(1)))

net=Path('/sys/class/net')
if net.exists():
    patterns=(
        re.compile(r'^mtun(\d+)$'),
        re.compile(r'^bh(\d+)$'),
        re.compile(r'^tp27[ktqa](\d+)$'),
    )
    for item in net.iterdir():
        for pattern in patterns:
            m=pattern.match(item.name)
            if m:
                ids.add(int(m.group(1)))
                break

for tid in sorted(ids):
    print(f'ID={tid}')
PY
""",
            timeout=45,
        )

        return _extract_runtime_ids(result.stdout)

    finally:
        conn.close()
        await conn.wait_closed()


def _cleanup_script(tid: int) -> str:
    tid = int(tid)
    relay_number = 100 + tid

    services = [
        f"twinpanel-mtunnel-{tid}.service",
        f"twinpanel-backhaul-{tid}.service",
        f"twinpanel-2027-kcp{tid}.service",
        f"twinpanel-2027-tcp{tid}.service",
        f"twinpanel-2027-quic{tid}.service",
        f"twinpanel-2027-arq{tid}.service",
        f"twinpanel-gost_tun-{tid}-iran.service",
        f"twinpanel-kernel_gre-{tid}-iran.service",
        f"twinpanel-mother-egress-{tid}-iran.service",
        f"twinpanel-backhaul-egress-{tid}-iran.service",
        f"twinpanel-backhaul-route-guardian-{tid}.service",
        f"tp{tid}-ssh.service",
        f"tp{tid}-exit-tun.service",
        f"tp{tid}-iran-tun.service",
        f"tp{tid}-relay-ssh.service",
        f"tp{tid}-relay-if.service",
        f"tp{tid}-relay-exit-if.service",
        f"tp{tid}-relay-hop.service",
        f"tp{tid}-relay-tls.service",
        f"tp{tid}-tls-client.service",
        f"tp{tid}-stunnel-client.service",
    ]

    service_words = " ".join(shlex.quote(item) for item in services)

    interfaces = [
        f"mtun{tid}"[:15],
        f"bh{tid}"[:15],
        f"tp27k{tid}"[:15],
        f"tp27t{tid}"[:15],
        f"tp27q{tid}"[:15],
        f"tp27a{tid}"[:15],
        f"tun{tid}"[:15],
        f"tun{relay_number}"[:15],
    ]
    interface_words = " ".join(shlex.quote(item) for item in interfaces)

    tables = [
        24000 + tid,
        24100 + tid,
        24200 + tid,
        24300 + tid,
        24400 + tid,
        25000 + tid,
        26000 + tid,
    ]
    table_words = " ".join(str(item) for item in tables)

    return f"""
set -eu

TID={tid}
SERVICES={shlex.quote(service_words)}
INTERFACES={shlex.quote(interface_words)}
TABLES={shlex.quote(table_words)}

for svc in $SERVICES; do
    systemctl disable --now "$svc" >/dev/null 2>&1 || true
    rm -f "/etc/systemd/system/$svc"
done

rm -rf \
  "/etc/twinpanel/ssh-relay/tunnel-$TID" \
  "/etc/twinpanel/tp$TID-ssh"

rm -f \
  "/etc/twinpanel/mtunnel/tunnel-$TID.json" \
  "/etc/twinpanel/backhaul/tunnel-$TID.toml" \
  "/usr/local/sbin/tp$TID-iran-up" \
  "/usr/local/sbin/tp$TID-exit-up" \
  "/usr/local/sbin/tp$TID-relay-iran-if" \
  "/usr/local/sbin/tp$TID-relay-exit-if"

for iface in $INTERFACES; do
    ip link del "$iface" >/dev/null 2>&1 || true
done

for table in $TABLES; do
    while ip -4 rule del priority "$table" >/dev/null 2>&1; do :; done
    ip -4 route flush table "$table" >/dev/null 2>&1 || true
done

# Remove only TwinPanel key comments owned by this now-absent tunnel id.
if [ -f /root/.ssh/authorized_keys ]; then
    python3 - "$TID" <<'PY2'
from pathlib import Path
import sys

tid=int(sys.argv[1])
p=Path('/root/.ssh/authorized_keys')
lines=p.read_text().splitlines()
tags=(
    f'tp{{tid}}-relay-hop',
    f'tp{{tid}}-relay-exit',
    f'tp{{tid}}-relay-hop-source-probe',
)
kept=[line for line in lines if not any(line.rstrip().endswith(tag) for tag in tags)]
p.write_text(('\n'.join(kept) + '\n') if kept else '')
PY2
    chmod 600 /root/.ssh/authorized_keys
fi

systemctl daemon-reload >/dev/null 2>&1 || true

bad=0
for svc in $SERVICES; do
    if systemctl is-active --quiet "$svc"; then
        echo "ACTIVE_SERVICE=$svc"
        bad=1
    fi
done

for iface in $INTERFACES; do
    if ip link show "$iface" >/dev/null 2>&1; then
        echo "LIVE_INTERFACE=$iface"
        bad=1
    fi
done

if [ "$bad" -ne 0 ]; then
    exit 61
fi

echo "CLEANED_TUNNEL_ID=$TID"
"""


async def _cleanup_orphan_on_node(node: Node, tid: int, db) -> None:
    conn = await ssh_connect_saved(node, db)

    try:
        result = await _run(
            conn,
            _cleanup_script(int(tid)),
            timeout=120,
        )

        print(
            f"[RuntimeReconciler] CLEANED node={int(node.id)} "
            f"tunnel={int(tid)} detail={result.stdout.strip()!r}",
            flush=True,
        )

    finally:
        conn.close()
        await conn.wait_closed()


async def reconcile_once(*, apply: bool = True) -> dict:
    db = SessionLocal()

    try:
        desired = _desired_tunnel_ids(db)
        nodes = _current_nodes(db)

        observed: dict[int, list[int]] = {}
        cleaned: dict[int, list[int]] = {}
        errors: dict[int, str] = {}

        active_confirmation_keys: set[tuple[int, int]] = set()

        for node in nodes:
            node_id = int(node.id)

            try:
                runtime_ids = await _inventory_node(node, db)
            except Exception as exc:
                errors[node_id] = f"inventory:{exc}"[:2500]
                print(
                    f"[RuntimeReconciler] INVENTORY_ERROR node={node_id} "
                    f"error={errors[node_id]!r}",
                    flush=True,
                )
                continue

            orphan_ids = sorted(runtime_ids - desired)
            observed[node_id] = orphan_ids

            if orphan_ids:
                print(
                    f"[RuntimeReconciler] ORPHANS node={node_id} "
                    f"ids={orphan_ids} desired={sorted(desired)}",
                    flush=True,
                )

            for tid in orphan_ids:
                key = (node_id, int(tid))
                active_confirmation_keys.add(key)
                _confirmations[key] += 1

                if not apply:
                    continue

                if _confirmations[key] < ORPHAN_CONFIRM_CYCLES:
                    print(
                        f"[RuntimeReconciler] CONFIRMING node={node_id} "
                        f"tunnel={int(tid)} "
                        f"cycle={_confirmations[key]}/{ORPHAN_CONFIRM_CYCLES}",
                        flush=True,
                    )
                    continue

                # Re-check the DB immediately before destructive cleanup.
                if db.get(Tunnel, int(tid)) is not None:
                    _confirmations.pop(key, None)
                    print(
                        f"[RuntimeReconciler] SKIP_REAPPEARED node={node_id} "
                        f"tunnel={int(tid)}",
                        flush=True,
                    )
                    continue

                try:
                    await _cleanup_orphan_on_node(
                        node,
                        int(tid),
                        db,
                    )
                    cleaned.setdefault(node_id, []).append(int(tid))
                    _confirmations.pop(key, None)
                except Exception as exc:
                    errors[node_id] = (
                        f"cleanup tunnel={int(tid)}:{exc}"
                    )[:2500]
                    print(
                        f"[RuntimeReconciler] CLEANUP_ERROR node={node_id} "
                        f"tunnel={int(tid)} error={str(exc)[:2000]!r}",
                        flush=True,
                    )

        for key in list(_confirmations):
            if key not in active_confirmation_keys:
                _confirmations.pop(key, None)

        return {
            "desired": sorted(desired),
            "observed": observed,
            "cleaned": cleaned,
            "errors": errors,
        }

    finally:
        db.close()


async def reconciler_loop() -> None:
    print(
        "TWINPANEL_RUNTIME_RECONCILER_START "
        f"interval={RECONCILE_INTERVAL_SECONDS}s "
        f"confirm_cycles={ORPHAN_CONFIRM_CYCLES}",
        flush=True,
    )

    await asyncio.sleep(RECONCILE_INITIAL_DELAY_SECONDS)

    while True:
        try:
            await reconcile_once(apply=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"[RuntimeReconciler] CYCLE_ERROR error={exc!r}",
                flush=True,
            )

        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
