from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "backend/app/protocol_account_registry.py"
PLAN_UI = ROOT / "components/legacy-plans-exact.tsx"
SUBSCRIPTION_UI = ROOT / "components/admin-manual-subscription-create.tsx"
SUBSCRIPTION_CLIENT = ROOT / "lib/subscription-protocol-api.ts"
SUBSCRIPTION_ROUTER = ROOT / "backend/app/routers/subscription_admin_v2.py"
SUBSCRIPTION_FACTORY = ROOT / "backend/app/services/subscription_factory.py"


def _tuple_assignment(source: str, name: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, tuple):
            raise AssertionError(f"{name} must remain a tuple")
        return tuple(str(item) for item in value)
    raise AssertionError(f"{name} assignment not found")


def main() -> None:
    registry_source = REGISTRY.read_text(encoding="utf-8")
    classic = _tuple_assignment(registry_source, "CLASSIC_PROTOCOL_KEYS")
    modern = _tuple_assignment(registry_source, "MODERN_PROTOCOL_KEYS")
    canonical = classic + modern

    assert len(classic) == 5, classic
    assert len(modern) == 10, modern
    assert len(canonical) == 15, canonical
    assert len(set(canonical)) == 15, canonical

    plan_ui = PLAN_UI.read_text(encoding="utf-8")
    assert "planProtocolApi" not in plan_ui
    assert "selectedProtocols" not in plan_ui
    assert "classicCatalog" not in plan_ui
    assert "modernCatalog" not in plan_ui
    assert "پروتکل در پلن تعریف نمی‌شود" in plan_ui
    assert "پروتکل‌ها هنگام ساخت هر اشتراک انتخاب می‌شوند" in plan_ui

    client = SUBSCRIPTION_CLIENT.read_text(encoding="utf-8")
    assert '"/v1/subscriptions/protocol-catalog"' in client

    router = SUBSCRIPTION_ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/protocol-catalog")' in router
    assert "registry_payload()" in router
    assert "requested_protocols = _canonical_protocols(payload.protocols)" in router
    assert "هنگام ساخت اشتراک حداقل یک پروتکل انتخاب کنید" in router

    factory = SUBSCRIPTION_FACTORY.read_text(encoding="utf-8")
    assert "requested_protocols = normalize_protocols(protocols)" in factory
    assert "plan_protocols" not in factory
    assert "protocol not in PROTOCOL_FIELDS" not in factory

    ui = SUBSCRIPTION_UI.read_text(encoding="utf-8")
    assert "subscriptionProtocolApi.catalog()" in ui
    assert 'item.family==="classic"' in ui
    assert 'item.family==="modern"' in ui
    assert "selectAllProtocols" in ui
    assert "clearProtocols" in ui
    assert "انتخاب همه ۱۵ پروتکل" in ui
    assert "protocols.length}/15" in ui
    assert "plan_id:planId||null" in ui

    print("SUBSCRIPTION_OWNED_PROTOCOL_SELECTION_OK")
    print("CLASSIC=" + ",".join(classic))
    print("MODERN=" + ",".join(modern))
    print("TOTAL=15")


if __name__ == "__main__":
    main()
