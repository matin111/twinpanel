"""Read-only checks for sing-box independent process lifecycle and rollback."""
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]

def main():
    parent=(ROOT/"scripts/twinpanel_modern_accounting_worker.py").read_text()
    child=(ROOT/"scripts/twinpanel_singbox_isolated_worker.py").read_text()
    for source in (parent,child):
        ast.parse(source)
    assert 'os.environ.setdefault("TP_SINGBOX_INDEPENDENT_WORKER", "1")' in parent
    assert 'singbox_proc = await asyncio.create_subprocess_exec(' in parent
    assert parent.index('singbox_proc = await asyncio.create_subprocess_exec(') < parent.index('workers = (')
    assert '_singbox_isolated_subprocess(singbox_proc)' in parent
    assert 'else (' in parent
    assert 'singbox_native_accounting_loop()' in parent
    assert 'proc.terminate()' in parent
    assert 'proc.kill()' in parent
    assert 'singbox.SINGBOX_ACCOUNTING_INTERVAL_SECONDS = 45.0' in child
    assert 'install_accounting_device_batch_cache()' in child
    assert 'asyncio.run(singbox.singbox_native_accounting_loop())' in child
    assert 'systemctl' not in child
    assert 'restart' not in child
    print("SINGBOX_INDEPENDENT_PROCESS_ISOLATION=PASS")

if __name__=="__main__":
    main()
