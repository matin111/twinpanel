"""Only explicitly scoped imported-account backfill may create missing node pairs."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.twinpanel_existing_node_backfill_v1 import parse_args

BASE = Path(__file__).resolve().parents[1]


def test_preview_is_default_and_apply_requires_exact_node_confirmation():
    options = parse_args(["--node-id", "13", "--protocol", "singbox"])
    assert options.node_id == 13 and options.apply is False
    assert options.max_pairs == 5 and options.max_cycles == 1
    with pytest.raises(SystemExit):
        parse_args(["--node-id", "13", "--protocol", "singbox", "--apply"])
    with pytest.raises(SystemExit):
        parse_args([
            "--node-id", "13", "--protocol", "singbox", "--apply",
            "--confirm-node-id", "11",
        ])
    enabled = parse_args([
        "--node-id", "13", "--protocol", "openvpn", "--apply",
        "--confirm-node-id", "13", "--max-pairs", "3",
    ])
    assert enabled.apply and enabled.max_pairs == 3
    for proto in ("v2ray", "xray", "grpc", "reality"):
        with pytest.raises(SystemExit):
            parse_args(["--node-id", "13", "--protocol", proto])


def test_batch_has_strict_budgets():
    for args in [
        ["--node-id", "13", "--protocol", "singbox", "--max-pairs", "91"],
        ["--node-id", "13", "--protocol", "singbox", "--max-pairs", "0"],
        ["--node-id", "13", "--protocol", "singbox", "--max-cycles", "99"],
        ["--node-id", "-1", "--protocol", "openvpn"],
    ]:
        with pytest.raises(SystemExit):
            parse_args(args)


def test_no_unbounded_per_account_provision_on_node_publish_path():
    v1 = (BASE / "app/routers/publish_node_all_users_v1.py").read_text()
    v2 = (BASE / "app/routers/publish_node_all_users_v2.py").read_text()
    assert "asyncio.create_task(_install_node_in_background" in v1
    block = v2.split("async def publish_node_to_all_users_v2",1)[1].split("@router.post",1)[0]
    assert "await sync_installed_node_to_subscriptions" not in block
    assert "await _sync_modern_node" not in block
    assert "active_subscriptions_reconciled\": 0" in block
    assert "db.commit()" in block


def test_imported_backfill_preserves_per_plan_protocol_entitlements():
    singbox = (BASE / "scripts/twinpanel_migration_singbox_batch.py").read_text()
    classic = (BASE / "scripts/twinpanel_migration_classic_sequential_v3.py").read_text()
    assert "if key not in selected:" in singbox
    assert "SubscriptionProtocol.protocol==PROTOCOL" in classic
    assert "Subscription.status==SubscriptionStatus.ACTIVE" in classic
    assert "Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes" in classic
    assert "MigrationImportRecord.source.in_(SOURCES)" in classic
    assert "MigrationImportRecord.source.in_(SOURCES)" in singbox


def test_one_node_per_run_and_no_secret_logging():
    wrapper = (BASE / "scripts/twinpanel_existing_node_backfill_v1.py").read_text()
    ast.parse(wrapper)
    assert "run_one_node(node_id, subscription_id=subscription_id, include_native=include_native)" in wrapper
    assert "one_node(db, node_id, subscription_id=subscription_id, include_native=include_native)" in wrapper
    assert "health_guard(args.max_load)" in wrapper
    assert "fcntl.LOCK_EX | fcntl.LOCK_NB" in wrapper
    assert "DRY_RUN_ONLY_NO_CREDENTIAL_WRITES" in wrapper
    assert "str(exc)" not in wrapper
    assert 'logging.getLogger("asyncssh").setLevel(logging.WARNING)' in wrapper


def test_single_subscription_canary_is_opt_in_and_validated():
    args = parse_args(["--node-id", "13", "--protocol", "singbox", "--subscription-id", "3594"])
    assert args.subscription_id == 3594
    assert args.apply is False
    for invalid in ("0", "-13"):
        with pytest.raises(SystemExit):
            parse_args(["--node-id", "13", "--protocol", "singbox", "--subscription-id", invalid])
    scoped = parse_args([
        "--node-id", "13", "--protocol", "singbox", "--subscription-id", "3594",
        "--apply", "--confirm-node-id", "13", "--max-pairs", "1",
    ])
    assert scoped.apply and scoped.subscription_id == 3594 and scoped.max_pairs == 1


def test_target_scope_is_applied_to_singbox_and_classic_queries():
    singbox = (BASE / "scripts/twinpanel_migration_singbox_batch.py").read_text()
    classic = (BASE / "scripts/twinpanel_migration_classic_sequential_v3.py").read_text()
    wrapper = (BASE / "scripts/twinpanel_existing_node_backfill_v1.py").read_text()
    assert "Subscription.id == int(subscription_id)" in singbox
    assert "Subscription.id==int(subscription_id)" in classic
    assert "subscription_id=subscription_id" in singbox
    assert "one_node(db, node_id, subscription_id=subscription_id, include_native=include_native)" in wrapper
    assert "eligible_count(db, args.node_id, args.protocol, args.subscription_id, args.include_native)" in wrapper
