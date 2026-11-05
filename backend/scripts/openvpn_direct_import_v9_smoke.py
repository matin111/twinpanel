"""Regression for direct OpenVPN import on subscription mobile hub."""
from pathlib import Path

app = Path(__file__).resolve().parents[1] / "app" / "routers"
hub = (app / "public_connection_hub_v9.py").read_text("utf-8")
files = (app / "public_connection_files_v9.py").read_text("utf-8")
compile(hub, "public_connection_hub_v9.py", "exec")
compile(files, "public_connection_files_v9.py", "exec")

assert "'openvpn://import-profile/'+profileUrl" in hub
assert "new URL(url,location.href).href" in hub
assert "actionLink('phone','وارد کردن مستقیم در OpenVPN Connect',importUrl)" in hub
assert "row.append(dl,phone)" in hub
assert "sendRealFile(url,filename,key)" in hub  # WireGuard fallback remains
assert '"openvpn": ("ovpn", "application/x-openvpn-profile")' in files
assert "'attachment; filename=" in files
assert "private, no-store" in files
print("OPENVPN_DIRECT_IMPORT_V9=PASS")
