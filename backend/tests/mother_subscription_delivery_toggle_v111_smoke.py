from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "app" / "mother_subscription_delivery_policy_v108.py"
CENTRAL = ROOT / "app" / "routers" / "central_account_delivery_runtime_v3.py"


def test_mother_toggle_filters_customer_delivery_without_disabling_provisioning():
    policy = POLICY.read_text(encoding="utf-8")
    central = CENTRAL.read_text(encoding="utf-8")

    assert "TWINPANEL_MOTHER_SUBSCRIPTION_DELIVERY_POLICY_V111" in policy
    assert "account_delivery._stored_info = _stored_info_with_mother_policy" in policy
    assert "if _subscription_can_use_mother(db, sub):" in policy
    assert "return _filter_mother_from_delivery(db, payload)" in policy

    # Mother must remain part of the immutable SubscriptionNode provisioning
    # snapshot. Access settings are checked only when building delivery output.
    snapshot = central.split("def subscription_snapshot_nodes", 1)[1].split(
        "def customer_delivery_item_is_usable", 1
    )[0]
    assert "SubscriptionNode.subscription_id == sub.id" in snapshot
    assert "Node.node_type == NodeType.EXIT" in snapshot
    assert "admin_can_use_mother" not in snapshot
    assert "reseller_can_use_mother" not in snapshot
