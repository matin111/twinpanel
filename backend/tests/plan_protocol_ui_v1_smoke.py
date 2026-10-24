from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "backend/app/protocol_account_registry.py"
PLANS_ROUTER = ROOT / "backend/app/routers/plans.py"
PLAN_UI = ROOT / "components/legacy-plans-exact.tsx"
PLAN_CLIENT = ROOT / "lib/plan-protocol-api.ts"


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

    plans_router = PLANS_ROUTER.read_text(encoding="utf-8")
    assert '"/protocol-catalog"' in plans_router
    assert '"/{plan_id}/protocols"' in plans_router
    assert "registry_payload()" in plans_router
    assert "replace_plan_protocols(db, plan.id, protocols)" in plans_router

    client = PLAN_CLIENT.read_text(encoding="utf-8")
    assert '"/v1/plans/protocol-catalog"' in client
    assert "`/v1/plans/${planId}/protocols`" in client
    assert 'method:"PUT"' in client
    assert "JSON.stringify({protocols})" in client

    ui = PLAN_UI.read_text(encoding="utf-8")
    assert "planProtocolApi.catalog()" in ui
    assert "planProtocolApi.get(id)" in ui
    assert "planProtocolApi.set(planId,selectedProtocols)" in ui
    assert 'item.family==="classic"' in ui
    assert 'item.family==="modern"' in ui
    assert "classicCatalog.map" in ui
    assert "modernCatalog.map" in ui
    assert 'href="/admin/modern-protocols"' in ui
    assert "catalog.length!==15" in ui

    legacy_literal = 'const protocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"]'
    assert legacy_literal not in ui, "plan UI must not use the legacy five-protocol list as authority"

    print("PLAN_PROTOCOL_UI_V1_OK")
    print("CLASSIC=" + ",".join(classic))
    print("MODERN=" + ",".join(modern))
    print("TOTAL=15")


if __name__ == "__main__":
    main()
