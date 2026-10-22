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

EXPECTED_ALL = {
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
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
}
EXPECTED_SINGBOX = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
}


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


def main() -> None:
    classic = set(literal_assignment(REGISTRY, "CLASSIC_PROTOCOL_KEYS"))
    modern = set(literal_assignment(REGISTRY, "MODERN_PROTOCOL_KEYS"))
    assert classic | modern == EXPECTED_ALL
    assert classic.isdisjoint(modern)
    assert len(classic) == 5
    assert len(modern) == 10

    singbox = set(literal_assignment(ROUTE, "SINGBOX_ACCOUNT_PROTOCOLS"))
    assert singbox == EXPECTED_SINGBOX
    controller = set(literal_assignment(ENFORCEMENT, "CONTROLLER_MODERN_PROTOCOLS"))
    assert controller == EXPECTED_SINGBOX

    route_text = ROUTE.read_text(encoding="utf-8")
    assert '@router.post("/v1/subscriptions/{subscription_id}/provision-account")' in route_text
    assert "_provision_modern_protocol" in route_text
    assert "apply_account" in route_text
    assert "unsupported" in route_text

    init_text = ROUTERS_INIT.read_text(encoding="utf-8")
    assert "install_modern_enforcement_hooks()" in init_text
    assert "_modern_account_delivery_v1_router" in init_text
    assert "include_router(_modern_account_delivery_v1_router)" in init_text
    assert "_modern_enforcement_runtime_v1_router" in init_text
    assert "include_router(_modern_enforcement_runtime_v1_router)" in init_text

    enforcement_text = ENFORCEMENT.read_text(encoding="utf-8")
    assert 'row.status = "controller_pending"' in enforcement_text
    assert 'payload["executor"] = _EXECUTOR' in enforcement_text
    assert 'row.status = "controller_processing"' in enforcement_text
    assert 'row.status = "succeeded"' in enforcement_text
    assert "await remove_account(conn, protocol, subscription_id)" in enforcement_text
    assert "await apply_account(conn, node, secret)" in enforcement_text
    assert "modern_enforcement_loop" in enforcement_text

    enforcement_route_text = ENFORCEMENT_ROUTE.read_text(encoding="utf-8")
    assert "APIRouter(lifespan=_lifespan)" in enforcement_route_text
    assert "modern_enforcement_loop" in enforcement_route_text

    singbox_text = SINGBOX.read_text(encoding="utf-8")
    assert 'REVOCATION_SENTINEL = "__twinpanel_revoked__"' in singbox_text
    assert "refusing to leave managed inbound without users" not in singbox_text
    assert "sentinel_password = secrets.token_urlsafe(48)" in singbox_text

    # Sales remains fail-closed until native quota collection is completed for
    # the cohort. Enforcement is now real, but fake/unknown usage accounting is
    # still forbidden.
    factory_fields = literal_assignment(FACTORY, "PROTOCOL_FIELDS")
    assert set(factory_fields) == classic

    print("MODERN_ACCOUNT_LIFECYCLE_V1_OK")
    print("canonical_protocols=15")
    print("singbox_account_drivers=6")
    print("controller_enforcement=6")
    print("sales_gate=fail_closed_until_native_quota")


if __name__ == "__main__":
    main()
