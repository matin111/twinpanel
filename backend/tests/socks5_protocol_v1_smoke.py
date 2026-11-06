"""SOCKS5 release safety smoke: no anonymous proxy, valid sing-box config, native quota."""

from pathlib import Path
import json
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1] / "app"
catalog = (root / "protocol_catalog.py").read_text()
runtime = (root / "modern_protocol_runtime_v2.py").read_text()
accounts = (root / "singbox_subscription_accounts.py").read_text()
enforcement = (root / "services/account_enforcement_v2.py").read_text()
accounting = (root / "services/singbox_native_accounting_v265.py").read_text()
registry = (root / "protocol_account_registry.py").read_text()

assert '"socks5": {' in catalog and '"default_port": 10808' in catalog
assert '"runtime_status": "ready"' in catalog
assert '"socks5"' in registry and '"socks5"' in enforcement
assert '"socks5"' in accounting
assert 'base["type"] = "socks"' in runtime
assert 'base["users"] = [{{"username": "twinpanel-bootstrap", "password": seed["password"]}}]' in runtime
assert 'base["network"] = "tcp"' not in runtime
assert '("socks" if PROTOCOL == "socks5" else PROTOCOL)' in accounts
assert '"username" if PROTOCOL in ("naive", "socks5")' in accounts
assert 'elif PROTOCOL in ("naive", "socks5")' in accounts
assert '"version"] = "5"' in accounts
assert '"password"] = secret.password' in accounts
assert '("socks" if protocol == "socks5" else protocol)' in accounting

sing_box = shutil.which("sing-box") or shutil.which("twinpanel-sing-box")
if sing_box:
    with tempfile.TemporaryDirectory(prefix="twinpanel-socks5-ci-") as temp:
        inbound = {
            "log": {"level": "warn"},
            "inbounds": [{
                "type": "socks", "tag": "twinpanel-socks5-in",
                "listen": "127.0.0.1", "listen_port": 10808,
                "users": [{"username": "ci-user", "password": "ci-ephemeral-secret"}],
            }],
            "outbounds": [{"type": "direct", "tag": "direct"}],
            "route": {"final": "direct"},
        }
        path = Path(temp) / "inbound.json"
        path.write_text(json.dumps(inbound))
        subprocess.run([sing_box, "check", "-c", str(path)], check=True,
                       capture_output=True, timeout=20)
        outbound = {
            "log": {"level": "warn"},
            "inbounds": [{
                "type": "mixed", "listen": "127.0.0.1",
                "listen_port": 2080, "tag": "mixed-in",
            }],
            "outbounds": [{
                "type": "socks", "tag": "socks-out", "server": "127.0.0.1",
                "server_port": 10808, "version": "5", "network": "tcp",
                "username": "ci-user", "password": "ci-ephemeral-secret",
            }],
            "route": {"final": "socks-out"},
        }
        path.write_text(json.dumps(outbound))
        subprocess.run([sing_box, "check", "-c", str(path)], check=True,
                       capture_output=True, timeout=20)

print("SOCKS5_AUTHENTICATED_PROTOCOL_SMOKE_OK")
