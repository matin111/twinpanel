"""Regression smoke for TwinConnect macOS links in admin and reseller bots."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
URL = "https://t.me/twin_connect1/8"

paths = {
    "learning": ROOT / "app" / "telegram_learning_center.py",
    "reseller": ROOT / "app" / "reseller_bot_runtime_owned.py",
    "admin": ROOT / "app" / "telegram_admin_ops_v1.py",
    "main_runtime": ROOT / "app" / "telegram_runtime_bot.py",
    "reseller_runtime": ROOT / "app" / "reseller_bot_runtime.py",
}
sources = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
for name, source in sources.items():
    ast.parse(source, filename=str(paths[name]))

learning = sources["learning"]
assert 'APPS["macos"].insert(0, {' in learning
assert '"key": "twinconnect_macos"' in learning
assert '"download": "' + URL + '"' in learning
assert '"macos": ("TwinConnect",' in learning
assert '"macos": "مک (Intel)"' in learning
assert 'title == "TwinConnect" and os_key == "macos"' in learning
assert "System Settings > Privacy & Security" in learning
assert "url=item[\"download\"]" in learning

# The shared learning center is registered by both bot runtimes.
assert 'register_learning_handlers(router, prefix="mlearn")' in sources["main_runtime"]
assert 'register_learning_handlers(router, prefix="rlearn")' in sources["reseller_runtime"]

# The private admin console and reseller main menu both expose the direct post.
assert 'text="💻 کانکشن هوشمند مک (Intel)", url="' + URL + '"' in sources["admin"]
assert 'text="💻 کانکشن هوشمند مک (Intel)",\n                    url="' + URL + '"' in sources["reseller"]

print("TELEGRAM_TWINCONNECT_MACOS_LINK_SMOKE=PASS")
