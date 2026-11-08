"""Regress independent Sudoku presence ownership and fail-safe old collector."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = {
        name: ROOT / relative
        for name, relative in {
            "worker": "scripts/twinpanel_sudoku_fast_presence_worker.py",
            "supervisor": "scripts/twinpanel_modern_accounting_worker.py",
            "legacy": "app/services/modern_quota_runtime_v314.py",
        }.items()
    }
    source = {name: path.read_text(encoding="utf8") for name, path in paths.items()}
    for value in source.values():
        ast.parse(value)
    assert 'canonical._collect_established_tcp_ports(conn)' in source["worker"]
    assert 'canonical._apply_sudoku_presence(' in source["worker"]
    assert 'fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)' in source["worker"]
    assert 'systemctl' not in source["worker"]
    assert 'TP_SUDOKU_INDEPENDENT_WORKER' in source["supervisor"]
    assert 'sudoku_proc = await asyncio.create_subprocess_exec(' in source["supervisor"]
    assert source["supervisor"].index('sudoku_proc = await asyncio.create_subprocess_exec(') < source["supervisor"].index('workers = (')
    assert '_sudoku_fast_subprocess(sudoku_proc)' in source["supervisor"]
    assert source["legacy"].count('if grouped.get("sudoku") and not SUDOKU_INDEPENDENT_WORKER:') == 2
    print("SUDOKU_FAST_PRESENCE_ISOLATION=PASS")


if __name__ == "__main__":
    main()
