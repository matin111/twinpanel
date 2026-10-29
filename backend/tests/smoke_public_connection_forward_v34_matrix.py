from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V13 = ROOT / "backend/app/routers/public_connection_modern_delivery_v13.py"
V34 = ROOT / "backend/app/routers/public_connection_forward_v34.py"
V30 = ROOT / "backend/app/routers/public_connection_protocol_subscriptions_v30.py"

MODES = (
    ("windows-wide", "windows"),
    ("windows-narrow", "windows"),
    ("android", "android"),
    ("ios", "ios"),
)

EXPECTED_CLIENTS = {
    "cisco": {"windows": "OpenConnect / Cisco Client", "android": "OpenConnect", "ios": "Cisco Secure Client"},
    "openvpn": {"windows": "OpenVPN Connect", "android": "OpenVPN Connect", "ios": "OpenVPN Connect"},
    "wireguard": {"windows": "WireGuard", "android": "WireGuard", "ios": "WireGuard"},
    "l2tp": {"windows": None, "android": None, "ios": None},
    "v2ray": {"windows": "Hiddify", "android": "Hiddify", "ios": "Hiddify"},
    "hysteria2": {"windows": "Karing", "android": "Karing", "ios": "Karing"},
    "tuic": {"windows": "Karing", "android": "Karing", "ios": "Karing"},
    "anytls": {"windows": "Karing", "android": "Karing", "ios": "Karing"},
    "naive": {"windows": "Karing", "android": "Karing", "ios": "Karing"},
    "shadowtls": {"windows": "Karing", "android": "Karing", "ios": "Karing"},
    "snell": {"windows": "sing-box Desktop", "android": "sing-box", "ios": "sing-box"},
    "mieru": {"windows": "Karing", "android": "Karing", "ios": "Karing"},
    "trusttunnel": {"windows": "TrustTunnel GUI", "android": "TrustTunnel", "ios": "TrustTunnel"},
    "amneziawg": {"windows": "AmneziaWG", "android": "AmneziaWG", "ios": "AmneziaWG"},
    "sudoku": {"windows": "Sudoku Desktop", "android": "Sudodroid", "ios": "Anywhere Proxy"},
}

PROVEN_SUBSCRIPTIONS = {"v2ray", "hysteria2", "tuic", "anytls"}
MANUAL = {"cisco", "l2tp"}
NATIVE_FILES = {"openvpn", "wireguard", "amneziawg"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assignment_values(source: str, names: tuple[str, ...]) -> dict[str, object]:
    tree = ast.parse(source)
    env: dict[str, object] = {}
    wanted = set(names)
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value = node.value
        if target not in wanted or value is None:
            continue
        env[target] = eval(compile(ast.Expression(value), "<v13-policy>", "eval"), {"__builtins__": {}}, env)
    missing = wanted - env.keys()
    require(not missing, f"missing assignments: {sorted(missing)}")
    return env


def js_set(source: str, variable: str) -> set[str]:
    match = re.search(rf"const\s+{re.escape(variable)}\s*=\s*new Set\(\[(.*?)\]\);", source, re.S)
    require(match is not None, f"JS set {variable} missing")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def python_tuple(source: str, variable: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value = node.value
        if target == variable and value is not None:
            return tuple(ast.literal_eval(value))
    raise AssertionError(f"{variable} missing")


def main() -> None:
    v13 = V13.read_text(encoding="utf-8")
    v34 = V34.read_text(encoding="utf-8")
    v30 = V30.read_text(encoding="utf-8")

    values = assignment_values(v13, ("_PLATFORMS", "_KARING", "_HIDDIFY", "CLIENTS"))
    clients = values["CLIENTS"]
    require(isinstance(clients, dict), "V13 CLIENTS is not a dict")

    classic = python_tuple(v13, "CLASSIC_PROTOCOLS")
    modern = python_tuple(v13, "MODERN_PROTOCOLS")
    inventory = classic + modern
    require(tuple(EXPECTED_CLIENTS) == inventory, f"15-protocol order drifted: {inventory!r}")

    subscription_ui = js_set(v34, "SUBSCRIPTIONS")
    require(subscription_ui == PROVEN_SUBSCRIPTIONS, f"bad V34 subscription cohort: {subscription_ui}")
    require(set(python_tuple(v30, "SUPPORTED_PROTOCOLS")) == PROVEN_SUBSCRIPTIONS,
            "V30 subscription cohort does not match UI")
    require(js_set(v34, "MANUAL") == MANUAL, "manual protocol policy drifted")
    require(js_set(v34, "NATIVE_FILES") == NATIVE_FILES, "native file protocol policy drifted")

    checked = 0
    for protocol in inventory:
        for mode, platform in MODES:
            expected = EXPECTED_CLIENTS[protocol][platform]
            actual = None
            url = None
            row = clients.get(protocol, {}).get(platform) if isinstance(clients.get(protocol, {}), dict) else None
            if row is not None:
                actual, url = row
            if expected is None:
                require(actual is None, f"{protocol}/{mode}: L2TP/native must not expose a separate client")
            else:
                require(actual == expected, f"{protocol}/{mode}: expected {expected!r}, got {actual!r}")
                require(isinstance(url, str) and bool(url.strip()), f"{protocol}/{mode}: missing client URL")

            if protocol in PROVEN_SUBSCRIPTIONS:
                require(protocol in subscription_ui, f"{protocol}/{mode}: proven subscription missing")
            else:
                require(protocol not in subscription_ui, f"{protocol}/{mode}: unproven subscription exposed")

            if mode == "windows-narrow":
                wide_expected = EXPECTED_CLIENTS[protocol]["windows"]
                require(expected == wide_expected, f"{protocol}: narrow Windows changed OS semantics")
            checked += 1

    require(checked == 60, f"expected 60 acceptance policy rows, got {checked}")
    require("MutationObserver" not in v34, "V34 must remain observer-free")
    require("کپی کانفیگ" not in v34, "ambiguous copy-config label returned")
    require("mobile-send-btn" in v34, "Windows mobile-send legacy action is not hidden")
    require("while(row.children.length>2)" in v34, "server action <=2 invariant missing")

    print(f"PUBLIC_CONNECT_FORWARD_V34_MATRIX=PASS rows={checked}")


if __name__ == "__main__":
    main()
