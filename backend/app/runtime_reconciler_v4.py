from __future__ import annotations

import shlex

from . import runtime_reconciler as v1
from . import runtime_reconciler_v3 as v3
from .routers.provision import ssh_connect_saved


# ============================================================
# TWINPANEL RUNTIME RECONCILER V4 - TP27 FAST
#
# Preserve V3's two-pass DB-authority guard and extend only the owned runtime
# inventory/cleanup surface for tp27_fast. Existing tunnel IDs remain protected.
# ============================================================


async def _inventory_node_v4(node, db) -> set[int]:
    ids = set(await v3._inventory_node_v3(node, db))

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
    pattern=re.compile(r'^twinpanel-tp27_fast-(\d+)-(?:iran|exit)\.service$')
    for path in root.iterdir():
        m=pattern.match(path.name)
        if m:
            ids.add(int(m.group(1)))
net=Path('/sys/class/net')
if net.exists():
    pattern=re.compile(r'^tp27(\d+)$')
    for item in net.iterdir():
        m=pattern.match(item.name)
        if m:
            ids.add(int(m.group(1)))
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


def _cleanup_script_v4(tid: int) -> str:
    tid = int(tid)
    base = v3._cleanup_script_v3(tid)
    service_iran = f"twinpanel-tp27_fast-{tid}-iran.service"
    service_exit = f"twinpanel-tp27_fast-{tid}-exit.service"
    iface = f"tp27{tid}"[:15]
    table = 29000 + (tid % 900)

    extra = f"""

# ------------------------------------------------------------
# TP27 Fast V91 orphan cleanup
# ------------------------------------------------------------
for svc in {shlex.quote(service_iran)} {shlex.quote(service_exit)}; do
    systemctl disable --now "$svc" >/dev/null 2>&1 || true
    rm -f "/etc/systemd/system/$svc"
done

ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true
while ip -4 rule del priority {table} >/dev/null 2>&1; do :; done
ip -4 route flush table {table} >/dev/null 2>&1 || true
rm -f \
  "/usr/local/sbin/tp27-fast-$TID-iran" \
  "/usr/local/sbin/tp27-fast-$TID-exit"

python3 - "$TID" <<'PY4'
import shlex
import subprocess
import sys

tid=int(sys.argv[1])
tags=(
    f'TwinPanel-tp27_fast-{{tid}}',
    f'TwinPanel-TP27-{{tid}}-',
)
for table in ('filter','nat'):
    prefix=['iptables']
    if table != 'filter':
        prefix += ['-t',table]
    out=subprocess.run(prefix+['-S'],capture_output=True,text=True,check=False).stdout
    for raw in out.splitlines():
        if not raw.startswith('-A ') or not any(tag in raw for tag in tags):
            continue
        try:
            parts=shlex.split(raw)
            parts[0]='-D'
            subprocess.run(prefix+parts,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        except Exception:
            pass
PY4

systemctl daemon-reload >/dev/null 2>&1 || true

if systemctl is-active --quiet {shlex.quote(service_iran)} || \
   systemctl is-active --quiet {shlex.quote(service_exit)} || \
   ip link show {shlex.quote(iface)} >/dev/null 2>&1; then
    echo "TP27_ORPHAN_CLEANUP_FAILED=$TID"
    exit 63
fi

echo "CLEANED_TP27_FAST_TUNNEL_ID=$TID"
"""
    return base + extra


def _activate_patch() -> None:
    v3._activate_patch()
    v1._inventory_node = _inventory_node_v4
    v1._cleanup_script = _cleanup_script_v4


async def reconcile_once(*, apply: bool = True) -> dict:
    _activate_patch()
    return await v1.reconcile_once(apply=apply)


async def reconciler_loop() -> None:
    _activate_patch()
    await v1.reconciler_loop()
