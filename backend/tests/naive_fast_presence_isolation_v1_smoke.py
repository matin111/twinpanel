"""Naive fast presence isolation and rollback regressions; no network calls."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    worker = (ROOT / "scripts/twinpanel_naive_fast_presence_worker.py").read_text()
    parent = (ROOT / "scripts/twinpanel_modern_accounting_worker.py").read_text()
    for source in (worker, parent):
        ast.parse(source)
    assert "native.collect_singbox_snapshot(conn)" in worker
    assert '"naive": devices' in worker
    assert "native._refresh_authenticated_live_presence(" in worker
    assert "install_accounting_device_batch_cache()" in worker
    assert "fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)" in worker
    assert "db.commit()" in worker
    assert "await asyncio.wait_for(conn.wait_closed(), timeout=3)" in worker
    assert "systemctl" not in worker
    assert "apply_usage_event(" not in worker
    assert "apply_singbox_snapshot(" not in worker
    assert 'os.environ.setdefault("TP_NAIVE_FAST_PRESENCE_WORKER", "1")' in parent
    assert 'naive_proc = await asyncio.create_subprocess_exec(' in parent
    assert parent.index('naive_proc = await asyncio.create_subprocess_exec(') < parent.index('workers = (')
    assert '_naive_fast_subprocess(naive_proc)' in parent
    assert "proc.terminate()" in parent
    print("NAIVE_ISOLATED_AUTHENTICATED_PRESENCE=PASS")


if __name__ == "__main__":
    main()
