from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "backend/app/routers/public_connection_device_actions_v11.py").read_text(encoding="utf-8")

assert "TWINPANEL_PUBLIC_CONNECT_KARING_DOWNLOADS_V50" in source
assert "tp-karing-recommended" in source
assert "grid.prepend(link)" in source
assert "data-client" not in source or "link.dataset.client='karing'" in source

expected = {
    "windows": "https://dot.karing.app/client.html?tag=windows-installer-stable",
    "macos": "https://dot.karing.app/client.html?tag=macos-stable",
    "android": "https://dot.karing.app/client.html?tag=android-stable",
    "ios": "https://apps.apple.com/us/app/karing/id6472431552",
    "linux": "https://dot.karing.app/client.html?tag=linux-deb-stable",
}

for platform, url in expected.items():
    assert platform in source, platform
    assert url in source, url

assert "دانلود مستقیم نسخه Stable ویندوز" in source
assert "دانلود مستقیم نسخه Stable اندروید" in source
assert "دانلود Karing از App Store" in source
assert "دانلود مستقیم Karing برای Debian / Ubuntu" in source

# Keep legacy/native client choices available; this feature only promotes a
# simple recommended app and does not alter protocol delivery or credentials.
for forbidden in [
    "iptables", "nft", "vxlan", "tp27", "quota", "accounting",
    "provision", "credential generation", "firewall",
]:
    assert forbidden not in source.lower(), forbidden

print("Public Connect Karing downloads V50 smoke: PASS")
