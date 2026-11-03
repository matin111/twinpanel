from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_fast_admin_edit_precedes_slow_lifecycle():
    source = (ROOT / "backend/app/routers/central_account_delivery_runtime_v3.py").read_text()
    fast = source.index("include_router(_subscription_admin_edit_fast_v1_router)")
    legacy = source.index("include_router(_subscription_protocol_lifecycle_v3_router)")
    assert fast < legacy


def test_fast_edit_preserves_legacy_empty_node_snapshot():
    source = (ROOT / "backend/app/routers/subscription_admin_edit_fast_v1.py").read_text()
    assert 'status_code=202' in source
    assert 'requested_node_ids or list(old_node_ids)' in source
    assert 'background_tasks.add_task(_reconcile_snapshot_background' in source


def test_publish_all_v2_precedes_v1_and_patches_background_installer():
    init_source = (ROOT / "backend/app/routers/__init__.py").read_text()
    v2 = init_source.index("include_router(_publish_node_all_users_v2_router)")
    v1 = init_source.index("include_router(_publish_node_all_users_v1_router)")
    assert v2 < v1

    source = (ROOT / "backend/app/routers/publish_node_all_users_v2.py").read_text()
    assert "subscriptions = query.all()" in source
    assert "SubscriptionNode(" in source
    assert "legacy_publish.publish_node_to_all_users = publish_node_to_all_users_v2" in source
