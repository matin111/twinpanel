from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "app" / "routers"


def _text(name: str) -> str:
    return (ROUTERS / name).read_text(encoding="utf-8")


def test_central_runtime_uses_subscription_node_snapshot() -> None:
    source = _text("central_account_delivery_runtime_v3.py")

    assert "SubscriptionNode.node_id == Node.id" in source
    assert "SubscriptionNode.subscription_id == sub.id" in source
    assert "Node.retired_at.is_(None)" in source
    assert "db.query(Node).filter(Node.retired_at.is_(None))" not in source


def test_store_and_reseller_share_modern_account_provisioner() -> None:
    source = _text("central_account_delivery_runtime_v3.py")

    assert "store_fulfillment.provision_account = provision_account_v1" in source
    assert "reseller_fulfillment.provision_account = provision_account_v1" in source
    assert "legacy_account_delivery.provision_account = provision_account_v1" in source


def test_runtime_bridge_is_installed_during_router_package_startup() -> None:
    package_source = _text("__init__.py")

    reseller_runtime = package_source.index("reseller_bot_delivery_runtime_v2")
    central_runtime = package_source.index("central_account_delivery_runtime_v3")
    modern_route = package_source.index(
        "_runtime_endpoints.router.include_router(_modern_account_delivery_v1_router)"
    )

    assert reseller_runtime < central_runtime < modern_route
