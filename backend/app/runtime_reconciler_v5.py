from __future__ import annotations

import shlex

from . import runtime_reconciler as v1
from . import runtime_reconciler_v4 as v4
from .routers.provision import ssh_connect_saved


# ============================================================
# TWINPANEL RUNTIME RECONCILER V5 - INDEPENDENT TP27 LANES
#
# Preserve V4's DB-authoritative two-pass cleanup and extend only the owned
# runtime inventory for the independent V149/V151 lanes:
#   * tp27_tcp_direct
#   * tp27_masque
#
# Existing Tunnel ids remain protected by the base reconciler. Shared carrier
# binaries are deliberately retained because they can be used by other Tunnel
# ids. Cleanup is scoped to exact service/interface/table/secret/firewall
# ownership for an already-absent Tunnel id.
# ============================================================


async def _inventory_node_v5(node, db) -> set[int]:
    ids = set(await v4._inventory_node_v4(node, db))

    conn = await ssh_connect_saved(node, db)
    try:
        result = await v1._run(
            conn,
            r"""
python3 - <<'PY'
from pathlib import Path
import re

ids=set()
root=Path('/etc/systemd/system')
if root.exists():
    pattern=re.compile(r'^twinpanel-(?:tp27_tcp_direct|tp27_masque)-(\d+)-(?:iran|exit)\.service$')
    for path in root.iterdir():
        m=pattern.match(path.name)
        if m:
            ids.add(int(m.group(1)))

net=Path('/sys/class/net')
if net.exists():
    patterns=(
        re.compile(r'^tp27t(\d+)$'),
        re.compile(r'^tp27m(\d+)$'),
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
        ids.update(v1._extract_runtime_ids(result.stdout))
        return ids
    finally:
        conn.close()
        await conn.wait_closed()


def _cleanup_script_v5(tid: int) -> str:
    tid = int(tid)
    base = v4._cleanup_script_v4(tid)

    direct_iran = f"twinpanel-tp27_tcp_direct-{tid}-iran.service"
    direct_exit = f"twinpanel-tp27_tcp_direct-{tid}-exit.service"
    masque_iran = f"twinpanel-tp27_masque-{tid}-iran.service"
    masque_exit = f"twinpanel-tp27_masque-{tid}-exit.service"

    direct_iface = f"tp27t{tid}"[:15]
    masque_iface = f"tp27m{tid}"[:15]
    direct_table = 30000 + (tid % 900)
    masque_table = 31000 + (tid % 900)

    services = " ".join(
        shlex.quote(value)
        for value in (direct_iran, direct_exit, masque_iran, masque_exit)
    )
    interfaces = " ".join(
        shlex.quote(value)
        for value in (direct_iface, masque_iface)
    )

    extra = f"""

# ------------------------------------------------------------
# Independent TP27 lane orphan cleanup V5
# ------------------------------------------------------------
for svc in {services}; do
    systemctl disable --now "$svc" >/dev/null 2>&1 || true
    rm -f "/etc/systemd/system/$svc"
done

for iface in {interfaces}; do
    ip link del "$iface" >/dev/null 2>&1 || true
done

while ip -4 rule del priority {direct_table} >/dev/null 2>&1; do :; done
ip -4 route flush table {direct_table} >/dev/null 2>&1 || true
while ip -4 rule del priority {masque_table} >/dev/null 2>&1; do :; done
ip -4 route flush table {masque_table} >/dev/null 2>&1 || true

rm -f \
  "/etc/twinpanel/tcp-direct/tunnel-$TID.token" \
  "/etc/twinpanel/masque/tunnel-$TID.token" \
  "/etc/twinpanel/masque/tunnel-$TID.crt" \
  "/etc/twinpanel/masque/tunnel-$TID.key"

python3 - "$TID" <<'PY5'
import shlex
import subprocess
import sys

tid=int(sys.argv[1])
tags=(
    f'TwinPanel-tp27_tcp_direct-{{tid}}',
    f'TwinPanel-TP27-TCP-{{tid}}',
    f'TwinPanel-tp27_masque-{{tid}}',
    f'TwinPanel-TP27-MASQUE-{{tid}}',
)

for table in ('filter','nat'):
    prefix=['iptables']
    if table != 'filter':
        prefix += ['-t',table]
    try:
        out=subprocess.run(prefix+['-S'],capture_output=True,text=True,check=False).stdout
    except Exception:
        continue
    for raw in out.splitlines():
        if not raw.startswith('-A ') or not any(tag in raw for tag in tags):
            continue
        try:
            parts=shlex.split(raw)
            parts[0]='-D'
            subprocess.run(
                prefix+parts,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass
PY5

systemctl daemon-reload >/dev/null 2>&1 || true

bad=0
for svc in {services}; do
    if systemctl is-active --quiet "$svc"; then
        echo "ACTIVE_TP27_LANE_SERVICE=$svc"
        bad=1
    fi
done
for iface in {interfaces}; do
    if ip link show "$iface" >/dev/null 2>&1; then
        echo "LIVE_TP27_LANE_INTERFACE=$iface"
        bad=1
    fi
done

if [ "$bad" -ne 0 ]; then
    exit 64
fi

echo "CLEANED_TP27_INDEPENDENT_LANES_TUNNEL_ID=$TID"
"""
    return base + extra


def _activate_patch() -> None:
    v4._activate_patch()
    v1._inventory_node = _inventory_node_v5
    v1._cleanup_script = _cleanup_script_v5


async def reconcile_once(*, apply: bool = True) -> dict:
    _activate_patch()
    return await v1.reconcile_once(apply=apply)


async def reconciler_loop() -> None:
    _activate_patch()
    await v1.reconciler_loop()
