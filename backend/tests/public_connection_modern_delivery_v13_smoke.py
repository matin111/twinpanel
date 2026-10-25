from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"

v13_path = ROUTERS / "public_connection_modern_delivery_v13.py"
live_path = ROUTERS / "public_connection_hub_live_v5.py"
standalone_path = ROOT / "backend" / "app" / "standalone_subscription_accounts.py"
singbox_path = ROOT / "backend" / "app" / "singbox_subscription_accounts.py"

v13 = v13_path.read_text(encoding="utf-8")
live = live_path.read_text(encoding="utf-8")
standalone = standalone_path.read_text(encoding="utf-8")
singbox = singbox_path.read_text(encoding="utf-8")

compile(v13, str(v13_path), "exec")
compile(live, str(live_path), "exec")
compile(standalone, str(standalone_path), "exec")

# Canonical customer delivery must cover every protocol that can be selected on
# a Subscription: five Classic + ten Modern.
tree = ast.parse(v13)
constants: dict[str, tuple[str, ...]] = {}
for node in tree.body:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        continue
    target = node.targets[0]
    if not isinstance(target, ast.Name):
        continue
    if target.id not in {"CLASSIC_PROTOCOLS", "MODERN_PROTOCOLS"}:
        continue
    constants[target.id] = tuple(ast.literal_eval(node.value))

classic = constants["CLASSIC_PROTOCOLS"]
modern = constants["MODERN_PROTOCOLS"]
assert classic == ("cisco", "openvpn", "wireguard", "l2tp", "v2ray")
assert modern == (
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
)
assert len(set(classic + modern)) == 15

# Desired state comes from SubscriptionProtocol. A selected-but-not-yet-ready
# protocol remains visible as pending instead of silently disappearing.
for marker in (
    "SubscriptionProtocol",
    "def _desired_protocols(",
    "v13-pending",
    "در انتظار ساخت کانفیگ",
    "Credential ساخته شده؛ مسیر Runtime هنوز آماده تحویل نیست",
    "هنوز قابل اتصال نیست",
):
    assert marker in v13, marker

# Ready cards are action-only. Do not bring back redundant claims that a config
# is "real" or generic prose that repeats what the buttons already communicate.
for stale_copy in (
    "کانفیگ واقعی آماده است",
    "برنامه مناسب همین دستگاه نمایش داده می‌شود.",
    "کانفیگ واقعی همین‌جا ظاهر می‌شود.",
):
    assert stale_copy not in v13, stale_copy
assert '<div class="v13-action-buttons">{primary}' in v13

# Public configuration retrieval is allowed only for an active subscription and
# only for a protocol that is still selected on that subscription.
for marker in (
    'if _status_value(sub) != "active":',
    'status_code=403',
    'if protocol not in _desired_protocols(db, int(sub.id)):',
    '"/{token}/modern-config/{protocol}/{node_id}"',
    'headers={',
    '"Cache-Control": "no-store"',
):
    assert marker in v13, marker

# Ready Modern protocols expose real import/config actions, not the old generic
# server/username/password facts. Classic facts must remain untouched.
assert '.protocol-panel[data-modern-protocol] .server-view>.facts{display:none}' in v13
assert "modern_protocol=protocol" in v13
classic_call = v13.index("_classic_client_action(protocol)")
classic_window = v13[classic_call - 180 : classic_call + 100]
assert "modern_protocol=" not in classic_window

# Sing-box cohort can one-click import into Karing. Snell intentionally remains
# on native sing-box because Karing Snell support is not treated as guaranteed.
assert "karing://install-config?url=" in v13
assert 'config_format == "sing-box" and protocol != "snell"' in v13
for protocol in ("hysteria2", "tuic", "anytls", "naive", "shadowtls"):
    assert f'"{protocol}": _KARING' in v13
assert '"snell": {' in v13
assert "sing-box Desktop" in v13

# Mieru receives a generated Karing-compatible profile while TrustTunnel keeps
# its real tt:// URI from provisioning. Sudoku gets both an upstream-compatible
# raw JSON endpoint and a canonical sudoku:// share URI.
for marker in (
    "def _mieru_karing_yaml(",
    '?profile=karing',
    'uri = str(item.get("uri") or "").strip()',
    'return "sudoku://" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")',
    'filename = f"twinpanel-{protocol}-{node_id}.conf"',
):
    assert marker in v13, marker
assert '"config_format": "trusttunnel-deeplink"' in standalone
assert '"uri": deeplink' in standalone
assert 'def _sudoku_endpoint(host: str, port: int) -> str:' in standalone
assert 'def _sudoku_share_uri(host: str, port: int, key: str, name: str) -> str:' in standalone
assert '"server_address": endpoint' in standalone
assert '"server_port": port' not in standalone
assert '"config_format": "sudoku-json"' in standalone
assert '"uri": sudoku_uri' in standalone
# Sudoku provisioning is not ready merely because systemd reports the
# process active. The account driver must wait for the per-user TCP
# listener to bind, otherwise an immediate client can race startup.
for marker in (
    'ready=0; ',
    'for i in $(seq 1 100); do ',
    'ss -H -lnt',
    'sleep 0.2; ',
    'if [ ${ready:-0} -ne 1 ]; then ',
    "Sudoku listener readiness timeout on :{port}",
    'journalctl -u {service}.service -n 30 --no-pager',
):
    assert marker in standalone, marker
assert '"config_format": "amneziawg"' in standalone
assert '"config_format": "mieru-json"' in standalone
assert '"config_format": "sing-box"' in singbox

# UI stays device-aware and uncluttered: only the detected Windows/Android/iOS/
# macOS client is shown; the old global app catalogue is hidden.
for marker in (
    "data-v13-platform",
    "return'ios'",
    "return'android'",
    "return'windows'",
    "return'macos'",
    "if(globalApps)globalApps.hidden=true",
):
    assert marker in v13, marker

# Official AmneziaWG destinations are platform-specific rather than reusing the
# Windows binary link on mobile/Apple platforms.
assert "org.amnezia.awg" in v13
assert "id6478942365" in v13
assert "amneziawg-windows-client/releases/latest" in v13

# V13 must be part of the actual live public route and run last after legacy
# refiners so it can normalize the final customer-facing UI.
for marker in (
    "public_connection_modern_delivery_v13_router",
    "router.include_router(public_connection_modern_delivery_v13_router)",
    "refine_public_connection_modern_delivery_v13(source, token, db)",
):
    assert marker in live, marker
assert live.index("refine_public_connection_windows_v12(source)") < live.index(
    "refine_public_connection_modern_delivery_v13(source, token, db)"
)

print("PUBLIC_CONNECTION_MODERN_DELIVERY_V13_SMOKE=PASS")
print("PROTOCOLS=" + ",".join(classic + modern))
print("DELIVERY=desired-visible-ready-importable")
print("SUDOKU_ENDPOINT=host-port")
print("SUDOKU_SHARE_URI=canonical")
print("DEVICE_UI=windows-android-ios-macos")
print("REDUNDANT_READY_COPY=REMOVED")
