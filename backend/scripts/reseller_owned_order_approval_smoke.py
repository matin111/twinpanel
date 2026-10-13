from __future__ import annotations

import ast
from pathlib import Path


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    approval_path = (
        backend_root
        / "app"
        / "routers"
        / "reseller_bot_orders_owned_v3.py"
    )
    owned_plans_path = backend_root / "app" / "reseller_owned_plans.py"

    approval_source = approval_path.read_text(encoding="utf-8")
    owned_plans_source = owned_plans_path.read_text(encoding="utf-8")

    approval_tree = ast.parse(approval_source)
    ast.parse(owned_plans_source)

    snapshot_keywords: set[str] | None = None

    for node in ast.walk(approval_tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "snapshot"
            for target in node.targets
        ):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        if not isinstance(call.func, ast.Name) or call.func.id != "SimpleNamespace":
            continue
        snapshot_keywords = {
            keyword.arg
            for keyword in call.keywords
            if keyword.arg is not None
        }
        break

    assert snapshot_keywords is not None, "approval snapshot SimpleNamespace not found"

    required = {
        "id",
        "reseller_id",
        "backing_plan_id",
        "title",
        "device_limit",
        "is_active",
        "traffic_gb",
        "duration_days",
        "sell_price_toman",
        "enable_cisco",
        "enable_openvpn",
        "enable_wireguard",
        "enable_l2tp",
        "enable_v2ray",
    }

    missing = sorted(required - snapshot_keywords)
    assert not missing, f"owned approval snapshot missing fields: {missing}"

    # The downstream creation result dereferences reseller_plan.title after the
    # subscription transaction commits, so the approval compatibility snapshot
    # must always provide it to avoid a false post-commit failure.
    assert '"plan_name": reseller_plan.title' in owned_plans_source
    assert "title=(" in approval_source
    assert "mapping.title" in approval_source

    print("RESELLER_OWNED_ORDER_APPROVAL_SNAPSHOT_OK")


if __name__ == "__main__":
    main()
