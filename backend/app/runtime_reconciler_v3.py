from __future__ import annotations

import shlex

from . import runtime_reconciler as v1
from . import runtime_reconciler_v2 as v2
from .routers.provision import ssh_connect_saved


# ============================================================
# TWINPANEL MULTI-TUNNEL ORPHAN RECONCILER V3
#
# V2 keeps all DB-authority and two-pass confirmation guards. V3 extends only
# the TwinPanel-owned inventory/cleanup surface for the four modern L3
# candidates introduced into Smart Auto:
#   kernel_gre / gost_tun / amneziawg / netrix
#
# Existing Tunnel ids remain untouchable. This path matters only when a crash or
# interrupted deletion leaves remote candidate runtime after the DB identity is
# already gone.
# ============================================================


_base_inventory_node = v1._inventory_node


async def _inventory_node_v3(node, db) -> set[int]:
    ids = set(
        await _base_inventory_node(
            node,
            db,
        )
    )

    conn = await ssh_connect_saved(
        node,
        db,
    )

    try:
        result = await v1._run(
            conn,
            r"""
python3 - <<'PY'
from pathlib import Path
import re

ids=set()

unit_patterns=(
    re.compile(r'^twinpanel-(?:kernel_gre|gost_tun|amneziawg|netrix)-(\d+)-(?:iran|exit)\.service$'),
)

root=Path('/etc/systemd/system')
if root.exists():
    for path in root.iterdir():
        for pattern in unit_patterns:
            m=pattern.match(path.name)
            if m:
                ids.add(int(m.group(1)))
                break

net=Path('/sys/class/net')
if net.exists():
    patterns=(
        re.compile(r'^tpgr(\d+)$'),
        re.compile(r'^tpgs(\d+)$'),
        re.compile(r'^tpaw(\d+)$'),
        re.compile(r'^tpnx(\d+)$'),
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

        ids.update(
            v1._extract_runtime_ids(
                result.stdout
            )
        )

        return ids

    finally:
        conn.close()
        await conn.wait_closed()


def _cleanup_script_v3(tid: int) -> str:
    tid = int(tid)
    base = v2._cleanup_script(tid)

    candidate_services = []
    for name in (
        "kernel_gre",
        "gost_tun",
        "amneziawg",
        "netrix",
    ):
        candidate_services.extend(
            (
                f"twinpanel-{name}-{tid}-iran.service",
                f"twinpanel-{name}-{tid}-exit.service",
            )
        )

    service_words = " ".join(
        shlex.quote(item)
        for item in candidate_services
    )

    interfaces = (
        f"tpgr{tid}"[:15],
        f"tpgs{tid}"[:15],
        f"tpaw{tid}"[:15],
        f"tpnx{tid}"[:15],
    )
    interface_words = " ".join(
        shlex.quote(item)
        for item in interfaces
    )

    tables = tuple(
        22000 + index * 1000 + (tid % 900)
        for index in range(4)
    )
    table_words = " ".join(
        str(item)
        for item in tables
    )

    extra = f"""

# ------------------------------------------------------------
# Smart Auto V21 candidate orphan cleanup
# ------------------------------------------------------------
CANDIDATE_SERVICES={shlex.quote(service_words)}
CANDIDATE_INTERFACES={shlex.quote(interface_words)}
CANDIDATE_TABLES={shlex.quote(table_words)}

for svc in $CANDIDATE_SERVICES; do
    systemctl disable --now "$svc" >/dev/null 2>&1 || true
    rm -f "/etc/systemd/system/$svc"
done

for iface in $CANDIDATE_INTERFACES; do
    ip link del "$iface" >/dev/null 2>&1 || true
done

for table in $CANDIDATE_TABLES; do
    while ip -4 rule del priority "$table" >/dev/null 2>&1; do :; done
    ip -4 route flush table "$table" >/dev/null 2>&1 || true
done

rm -f \
  "/usr/local/sbin/tp-gre-$TID-iran" \
  "/usr/local/sbin/tp-gre-$TID-exit" \
  "/etc/twinpanel/amneziawg/tunnel-$TID.key" \
  "/etc/twinpanel/amneziawg/tunnel-$TID-iran.conf" \
  "/etc/twinpanel/amneziawg/tunnel-$TID-exit.conf" \
  "/etc/twinpanel/netrix/tunnel-$TID-iran.yaml" \
  "/etc/twinpanel/netrix/tunnel-$TID-exit.yaml"

# Delete only iptables rules carrying exact TwinPanel candidate ownership tags
# for this absent tunnel. Shared/global firewall state is never flushed.
python3 - "$TID" <<'PY3'
import shlex
import subprocess
import sys

tid=int(sys.argv[1])
tags=(
    f'TwinPanel-kernel_gre-{{tid}}',
    f'TwinPanel-gost_tun-{{tid}}',
    f'TwinPanel-amneziawg-{{tid}}',
    f'TwinPanel-netrix-{{tid}}',
    f'TwinPanel-GRE-{{tid}}-',
    f'TwinPanel-GOST-{{tid}}',
    f'TwinPanel-AWG-{{tid}}',
    f'TwinPanel-Netrix-{{tid}}',
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
        if not raw.startswith('-A '):
            continue
        if not any(tag in raw for tag in tags):
            continue
        try:
            parts=shlex.split(raw)
            parts[0]='-D'
            subprocess.run(prefix+parts,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        except Exception:
            pass
PY3

systemctl daemon-reload >/dev/null 2>&1 || true

candidate_bad=0
for svc in $CANDIDATE_SERVICES; do
    if systemctl is-active --quiet "$svc"; then
        echo "ACTIVE_CANDIDATE_SERVICE=$svc"
        candidate_bad=1
    fi
done

for iface in $CANDIDATE_INTERFACES; do
    if ip link show "$iface" >/dev/null 2>&1; then
        echo "LIVE_CANDIDATE_INTERFACE=$iface"
        candidate_bad=1
    fi
done

if [ "$candidate_bad" -ne 0 ]; then
    exit 62
fi

echo "CLEANED_SMART_CANDIDATES_TUNNEL_ID=$TID"
"""

    return base + extra


def _activate_patch() -> None:
    # First preserve V2's serializer fix, then extend only inventory/cleanup.
    v2._activate_patch()
    v1._inventory_node = _inventory_node_v3
    v1._cleanup_script = _cleanup_script_v3


async def reconcile_once(*, apply: bool = True) -> dict:
    _activate_patch()
    return await v1.reconcile_once(
        apply=apply
    )


async def reconciler_loop() -> None:
    _activate_patch()
    await v1.reconciler_loop()
