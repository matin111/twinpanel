"""Regression smoke for one unified Telegram learning/download entry point.

TwinConnect platform downloads, including macOS Intel, must remain inside the
shared app-first learning flow instead of adding separate main-menu shortcuts.
"""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
URL = "https://t.me/twin_connect1/8"

paths = {
    "learning": ROOT / "app" / "telegram_learning_center.py",
    "main_menu": ROOT / "app" / "telegram_account_link_bot.py",
    "main_menu_base": ROOT / "app" / "telegram_account_link_bot_original.py",
    "reseller": ROOT / "app" / "reseller_bot_runtime_owned.py",
    "admin": ROOT / "app" / "telegram_admin_ops_v1.py",
    "main_runtime": ROOT / "app" / "telegram_runtime_bot.py",
    "main_runtime_custom": ROOT / "app" / "telegram_runtime_custom.py",
    "reseller_runtime": ROOT / "app" / "reseller_bot_runtime.py",
    "reseller_wallet": ROOT / "app" / "reseller_bot_wallet_menu_runtime.py",
    "guides": ROOT / "app" / "telegram_guides_bot.py",
}
sources = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
trees = {}
for name, source in sources.items():
    trees[name] = ast.parse(source, filename=str(paths[name]))


def function_source(module_name: str, function_name: str) -> str:
    tree = trees[module_name]
    node = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    return ast.get_source_segment(sources[module_name], node) or ""


learning = sources["learning"]
assert 'APPS["macos"].insert(0, {' in learning
assert '"key": "twinconnect_macos"' in learning
assert '"download": "' + URL + '"' in learning
assert '"macos": ("TwinConnect",' in learning
assert '"macos": "مک (Intel)"' in learning
assert 'title == "TwinConnect" and os_key == "macos"' in learning
assert "System Settings > Privacy & Security" in learning
assert 'url=item["download"]' in learning

# Every active and fallback main-menu surface exposes exactly one combined
# learning/download button. The platform/app detail owns its download link.
menus = {
    "main inline": (function_source("main_menu", "_main_menu_keyboard"), "mlearn:g:root"),
    "main base": (function_source("main_menu_base", "_main_menu_keyboard"), "mlearn:g:root"),
    "admin": (function_source("admin", "_home"), "mlearn:g:root"),
    "reseller inline": (function_source("reseller", "reseller_main_keyboard"), "rlearn:g:root"),
    "main reply": (function_source("main_runtime", "main_keyboard"), None),
    "main styled reply": (function_source("main_runtime_custom", "_styled_main_keyboard"), None),
    "reseller reply fallback": (function_source("reseller_runtime", "_main_keyboard"), None),
    "reseller wallet fallback": (function_source("reseller_wallet", "wallet_main_keyboard"), None),
}
for name, (menu, callback) in menus.items():
    assert menu.count("آموزش و دانلود") == 1, name
    assert "⬇️ دانلود برنامه" not in menu, name
    if callback:
        assert callback in menu, name

# Old menu labels remain compatible while the new unified label routes to the
# same app-first guide; downloads are offered inside each selected app page.
assert '(F.text == "📚 آموزش و دانلود") | (F.text == "📚 آموزش")' in learning
assert "F.text == \"⬇️ دانلود برنامه\"" in learning
assert '(F.text=="📚 آموزش و دانلود") | (F.text=="📚 آموزش")' in sources["guides"]

# The shared learning center remains registered by both bot runtimes.
assert 'register_learning_handlers(router, prefix="mlearn")' in sources["main_runtime"]
assert 'register_learning_handlers(router, prefix="rlearn")' in sources["reseller_runtime"]

print("TELEGRAM_UNIFIED_LEARNING_DOWNLOAD_SMOKE=PASS")
