from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "backend/app/protocol_account_registry.py"
PLAN_UI = ROOT / "components/legacy-plans-exact.tsx"
PLAN_ROUTER = ROOT / "backend/app/routers/plans.py"
PLAN_TEMPLATE = ROOT / "backend/app/plan_template_selection.py"
PLAN_NODE_MODEL = ROOT / "backend/app/plan_node_models.py"
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

    # Plans are allowed to define a creation template/allow-list, but that
    # template must never replace SubscriptionProtocol/SubscriptionNode as the
    # runtime desired-state consumed by provisioning.
    plan_ui = PLAN_UI.read_text(encoding="utf-8")
    for label in (
        "Cisco / OpenConnect",
        "OpenVPN",
        "WireGuard",
        "L2TP / IPsec",
        "V2Ray / Xray",
        "Hysteria2",
        "TUIC",
        "AnyTLS",
        "NaiveProxy",
        "ShadowTLS",
        "Snell",
        "Mieru",
        "TrustTunnel",
        "AmneziaWG",
        "Sudoku",
    ):
        assert label in plan_ui, label
    assert "Allowed servers" in plan_ui
    assert "node_ids" in plan_ui
    assert "protocols" in plan_ui
    assert "snapshotted onto each subscription" in plan_ui

    plan_router = PLAN_ROUTER.read_text(encoding="utf-8")
    assert "replace_plan_template_protocols" in plan_router
    assert "replace_plan_nodes" in plan_router
    assert '"selection_scope": "plan_template_snapshot"' in plan_router
    assert '@router.get("/{plan_id}/protocols"' in plan_router
    assert '@router.put("/{plan_id}/protocols"' in plan_router
    assert '@router.get("/{plan_id}/nodes"' in plan_router
    assert '@router.put("/{plan_id}/nodes"' in plan_router

    template = PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert "explicit_plan_protocols" in template
    assert "ALL_PROTOCOL_KEYS" in template
    assert "PlanNode" in template
    assert "all_active_node_ids" in template

    node_model = PLAN_NODE_MODEL.read_text(encoding="utf-8")
    assert '__tablename__ = "plan_nodes"' in node_model
    assert 'UniqueConstraint("plan_id", "node_id"' in node_model
    assert "Runtime delivery remains subscription-owned" in node_model

    client = SUBSCRIPTION_CLIENT.read_text(encoding="utf-8")
    assert '"/v1/subscriptions/protocol-catalog"' in client

    router = SUBSCRIPTION_ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/protocol-catalog")' in router
    assert "registry_payload()" in router
    assert "requested_protocols = _canonical_protocols(payload.protocols)" in router
    assert "هنگام ساخت اشتراک حداقل یک پروتکل انتخاب کنید" in router

    factory = SUBSCRIPTION_FACTORY.read_text(encoding="utf-8")
    assert "requested_protocols = normalize_protocols(protocols)" in factory
    assert "allowed_protocols = plan_template_protocols" in factory
    assert "plan_template_node_ids" in factory
    assert "requested_node_ids = _unique_node_ids" in factory
    assert "SubscriptionProtocol(" in factory
    assert "SubscriptionNode(" in factory
    assert "protocol not in PROTOCOL_FIELDS" not in factory
    assert "CLASSIC_PROTOCOL_KEYS" in factory
    assert "if protocol not in CLASSIC_PROTOCOL_KEYS" in factory
    # A Plan must be read only while creating the subscription snapshot. The
    # runtime delivery path must remain subscription-owned afterwards.
    assert "PlanProtocol" not in factory
    assert "PlanNode(" not in factory

    ui = SUBSCRIPTION_UI.read_text(encoding="utf-8")
    assert "subscriptionProtocolApi.catalog()" in ui
    assert 'item.family==="classic"' in ui
    assert 'item.family==="modern"' in ui
    assert "selectAllProtocols" in ui
    assert "clearProtocols" in ui
    assert "انتخاب همه ۱۵ پروتکل" in ui
    assert "لغو انتخاب همه" in ui
    assert "protocols.length}/15" in ui
    assert "plan_id:planId||null" in ui

    print("SUBSCRIPTION_OWNED_PROTOCOL_SELECTION_OK")
    print("PLAN_TEMPLATE_SNAPSHOT_OK")
    print("CLASSIC=" + ",".join(classic))
    print("MODERN=" + ",".join(modern))
    print("TOTAL=15")


if __name__ == "__main__":
    main()
