"""Regression for isolated Mieru online presence worker.

No node connections or writes are performed by this test.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    dedicated_path = ROOT / "scripts/twinpanel_mieru_fast_presence_worker.py"
    parent_path = ROOT / "scripts/twinpanel_modern_accounting_worker.py"
    slow_path = ROOT / "app/services/modern_quota_runtime_v314.py"

    files = {
        "dedicated": dedicated_path.read_text(encoding="utf-8"),
        "parent": parent_path.read_text(encoding="utf-8"),
        "slow": slow_path.read_text(encoding="utf-8"),
    }
    for source in files.values():
        ast.parse(source)

    dedicated = files["dedicated"]
    assert 'INTERVAL_SECONDS = 20.0' in dedicated
    assert 'canonical._collect_mieru(conn)' in dedicated
    assert 'canonical._apply_mieru_presence(' in dedicated
    assert 'db.commit()' in dedicated
    assert 'await asyncio.wait_for(' in dedicated
    assert 'canonical.build_node_devices(db, node_id)' in dedicated
    assert 'if str(item.get("protocol") or "").lower() == "mieru"' in dedicated
    assert 'fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)' in dedicated
    assert 'conn.wait_closed()' in dedicated
    assert 'ssh_connect' not in dedicated
    assert 'systemctl' not in dedicated
    assert 'restart' not in dedicated
    assert 'openvpn' not in dedicated
    assert 'shadowtls' not in dedicated
    parent = files["parent"]
    assert 'os.environ.setdefault("TP_MIERU_INDEPENDENT_WORKER", "1")' in parent
    assert '_mieru_fast_subprocess(fast_proc)' in parent
    assert 'fast_proc = await asyncio.create_subprocess_exec(' in parent
    assert parent.index('fast_proc = await asyncio.create_subprocess_exec(') < parent.index('workers = (')
    assert 'proc.terminate()' in parent
    assert 'proc.kill()' in parent
    slow = files["slow"]
    assert 'MIERU_INDEPENDENT_WORKER = os.getenv(' in slow
    assert slow.count('if grouped.get("mieru") and not MIERU_INDEPENDENT_WORKER:') == 2
    print("MIERU_FAST_ISOLATION_REGRESSION=PASS")


if __name__ == "__main__":
    main()
