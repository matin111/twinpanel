from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "backend/app/protocol_account_registry.py"
FACTORY = ROOT / "backend/app/services/subscription_factory.py"
ROUTE = ROOT / "backend/app/routers/modern_account_delivery_v1.py"
ENFORCEMENT_ROUTE = ROOT / "backend/app/routers/modern_enforcement_runtime_v1.py"
ENFORCEMENT = ROOT / "backend/app/services/modern_enforcement_v1.py"
ROUTERS_INIT = ROOT / "backend/app/routers/__init__.py"
SINGBOX = ROOT / "backend/app/singbox_subscription_accounts.py"
STANDALONE = ROOT / "backend/app/standalone_subscription_accounts.py"
QUOTA_SCHEMA = ROOT / "backend/app/quota_schemas.py"
QUOTA_SYNC = ROOT / "backend/app/services/quota_node_sync.py"

EXPECTED_ALL = {
    "cisco", "openvpn", "wireguard", "l2tp", "v2ray",
    "hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell",
    "mieru", "trusttunnel", "amneziawg", "sudoku",
}
EXPECTED_SINGBOX = {"hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell"}
EXPECTED_STANDALONE = {"mieru", "trusttunnel", "amneziawg", "sudoku"}


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def literal_assignment(path: Path, name: str):
    tree = parse(path)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "frozenset":
            value = value.args[0]
        return ast.literal_eval(value)
    raise AssertionError(f"assignment not found: {path}:{name}")


def protocol_literal_values(path: Path) -> set[str]:
    tree = parse(path)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "ProtocolName" for target in node.targets):
            continue
        value = node.value
        if not isinstance(value, ast.Subscript) or not isinstance(value.slice, ast.Tuple):
            raise AssertionError("ProtocolName must remain an explicit Literal")
        return {
            str(item.value)
            for item in value.slice.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
    raise AssertionError("ProtocolName not found")


def main() -> None:
    classic = set(literal_assignment(REGISTRY, "CLASSIC_PROTOCOL_KEYS"))
    modern = set(literal_assignment(REGISTRY, "MODERN_PROTOCOL_KEYS"))
    assert classic | modern == EXPECTED_ALL
    assert classic.isdisjoint(modern)
    assert len(classic) == 5 and len(modern) == 10

    route_singbox = set(literal_assignment(ROUTE, "SINGBOX_ACCOUNT_PROTOCOLS"))
    route_standalone = set(literal_assignment(ROUTE, "STANDALONE_ACCOUNT_PROTOCOLS"))
    assert route_singbox == EXPECTED_SINGBOX
    assert route_standalone == EXPECTED_STANDALONE
    assert route_singbox | route_standalone == modern

    enforce_singbox = set(literal_assignment(ENFORCEMENT, "SINGBOX_MODERN_PROTOCOLS"))
    enforce_standalone = set(literal_assignment(ENFORCEMENT, "STANDALONE_MODERN_PROTOCOLS"))
    assert enforce_singbox == EXPECTED_SINGBOX
    assert enforce_standalone == EXPECTED_STANDALONE

    standalone_driver = set(literal_assignment(STANDALONE, "STANDALONE_ACCOUNT_PROTOCOLS"))
    assert standalone_driver == EXPECTED_STANDALONE

    route_text = ROUTE.read_text(encoding="utf-8")
    assert '@router.post("/v1/subscriptions/{subscription_id}/provision-account")' in route_text
    assert "_provision_modern_protocol" in route_text
    assert "new_account_secret" in route_text
    assert "MODERN_ACCOUNT_PROTOCOLS" in route_text

    init_text = ROUTERS_INIT.read_text(encoding="utf-8")
    assert "install_modern_enforcement_hooks()" in init_text
    assert "include_router(_modern_account_delivery_v1_router)" in init_text
    assert "include_router(_modern_enforcement_runtime_v1_router)" in init_text

    enforcement_text = ENFORCEMENT.read_text(encoding="utf-8")
    assert 'row.status = "controller_pending"' in enforcement_text
    assert 'payload["executor"] = _EXECUTOR' in enforcement_text
    assert "STANDALONE_MODERN_PROTOCOLS" in enforcement_text
    assert "controller_standalone_revoked" in enforcement_text
    assert "controller_standalone_restored" in enforcement_text
    assert "modern_enforcement_loop" in enforcement_text

    enforcement_route_text = ENFORCEMENT_ROUTE.read_text(encoding="utf-8")
    assert "APIRouter(lifespan=_lifespan)" in enforcement_route_text
    assert "modern_enforcement_loop" in enforcement_route_text

    singbox_text = SINGBOX.read_text(encoding="utf-8")
    assert 'REVOCATION_SENTINEL = "__twinpanel_revoked__"' in singbox_text
    assert "sentinel_password = secrets.token_urlsafe(48)" in singbox_text

    standalone_text = STANDALONE.read_text(encoding="utf-8")
    assert "mita replace config" in standalone_text
    assert "trusttunnel_endpoint" in standalone_text
    assert "10.254.0.1/16" in standalone_text
    assert "twinpanel-sudoku-sub-" in standalone_text
    assert "sudoku_master_public_key" in standalone_text

    quota_protocols = protocol_literal_values(QUOTA_SCHEMA)
    assert modern <= quota_protocols
    quota_mapping = literal_assignment(QUOTA_SYNC, "_PROTOCOL_TO_QUOTA")
    for protocol in modern:
        assert quota_mapping.get(protocol) == protocol

    # Account + revoke are now real for ten Modern protocols. Sales remains
    # fail-closed until runtime counter collectors are verified; zero-usage
    # fabrication is never an acceptable bridge.
    factory_fields = literal_assignment(FACTORY, "PROTOCOL_FIELDS")
    assert set(factory_fields) == classic

    print("MODERN_ACCOUNT_LIFECYCLE_V1_OK")
    print("canonical_protocols=15")
    print("modern_account_drivers=10")
    print("controller_enforcement=10")
    print("quota_contract=10_fail_closed")
    print("sales_gate=fail_closed_until_native_quota")


if __name__ == "__main__":
    main()
