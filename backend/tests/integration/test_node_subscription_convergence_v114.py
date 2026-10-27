import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _load_helper(name: str, namespace: dict | None = None):
    source = _text("backend/app/node_subscription_convergence_v114.py")
    tree = ast.parse(source)
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    module = ast.Module(body=[helper], type_ignores=[])
    scope = {"Any": Any}
    scope.update(namespace or {})
    exec(compile(module, "node_subscription_convergence_v114.py", "exec"), scope)
    return scope[name]


def _load_age_seconds():
    return _load_helper("_age_seconds", {"datetime": datetime})


def test_fresh_exit_install_keeps_historical_subscription_autosync():
    provision = _text("backend/app/routers/provision.py")
    delivery = _text("backend/app/routers/account_delivery.py")

    assert "TWINPANEL_INSTALLED_NODE_SUBSCRIPTION_AUTOSYNC_CALL_V1" in provision
    assert "sync_installed_node_to_subscriptions" in provision
    assert "await sync_installed_node_to_subscriptions" in provision

    assert "all_subscriptions = (" in delivery
    assert "db.query(\n            Subscription" in delivery
    assert "SubscriptionNode(" in delivery
    assert "SubscriptionNode.subscription_id" in delivery
    assert "SubscriptionNode.node_id" in delivery

    # Every historical subscription receives membership. Real VPN credentials
    # are provisioned only for active subscriptions and only for protocols that
    # the new Exit actually enables.
    assert "active_ids = [" in delivery
    assert '== "active"' in delivery
    for protocol, attr in {
        "cisco": "enable_cisco",
        "openvpn": "enable_openvpn",
        "wireguard": "enable_wireguard",
        "l2tp": "enable_l2tp",
        "v2ray": "enable_v2ray",
    }.items():
        assert f'"{protocol}":' in delivery
        assert f'"{attr}"' in delivery

    # Existing node items must be preserved and the new node must be idempotent.
    assert "cleaned_items.append(" in delivery
    assert "already_exists = any(" in delivery
    assert "reused_pairs += 1" in delivery
    assert "items.append(" in delivery
    assert "cred.config_text_encrypted = (\n                _enc(items)" in delivery


def test_node_access_grace_age_supports_naive_and_timezone_aware_datetimes():
    age_seconds = _load_age_seconds()

    naive = datetime.utcnow() - timedelta(seconds=240)
    aware_utc = datetime.now(timezone.utc) - timedelta(seconds=240)
    aware_offset = datetime.now(timezone(timedelta(hours=3, minutes=30))) - timedelta(seconds=240)

    for value in (naive, aware_utc, aware_offset):
        age = age_seconds(value)
        assert 230 <= age <= 250


def test_legacy_nullable_plan_id_is_safe_for_signature_and_modern_delivery():
    optional_int = _load_helper("_optional_int")
    runtime = _text("backend/app/node_subscription_convergence_v114.py")

    assert optional_int(None) is None
    assert optional_int(17) == 17
    assert optional_int("23") == 23

    # Production had at least one historical Subscription.plan_id=NULL. It must
    # stay visible to the topology fingerprint without crashing int(None).
    assert "_optional_int(row.plan_id)" in runtime
    assert "int(row.plan_id)" not in runtime

    # A NULL plan has no entitlement boundary, so Modern provisioning skips
    # secret creation for that orphaned legacy row but does not fail the worker.
    assert "plan_id = _optional_int(sub.plan_id)" in runtime
    assert "if plan_id is None:" in runtime
    assert "skipped_missing_plan += 1" in runtime
    assert '"skipped_missing_plan": skipped_missing_plan' in runtime
    assert "TWINPANEL_DYNAMIC_SUBSCRIPTION_DELIVERY_NULL_PLAN_V297" in runtime


def test_topology_changes_reconverge_classic_and_modern_delivery():
    runtime = _text("backend/app/node_subscription_convergence_v114.py")
    composition = _text("backend/app/self_hosted_runtime.py")

    assert "TWINPANEL_NODE_SUBSCRIPTION_CONVERGENCE_V114" in runtime
    assert "TWINPANEL_DYNAMIC_SUBSCRIPTION_DELIVERY_V294" in runtime
    assert "TWINPANEL_DYNAMIC_SUBSCRIPTION_DELIVERY_TIMEZONE_V295" in runtime
    assert "TWINPANEL_DYNAMIC_SUBSCRIPTION_DELIVERY_NULL_PLAN_V297" in runtime
    assert "_topology_signature" in runtime
    assert "Node.retired_at.is_(None)" in runtime
    assert "Node.node_type == NodeType.EXIT" in runtime
    assert "Node.status == NodeStatus.ONLINE" in runtime
    assert "Node.show_to_users.is_(True)" in runtime
    assert "NodeAccess.created_at" in runtime
    assert "_NEW_ACCESS_GRACE_SECONDS = 180" in runtime
    assert "age = _age_seconds(access_created_at)" in runtime

    # A successful node is not permanently cached anymore. Any material change
    # to nodes, tunnels, runtime configs, selected protocols, plan entitlements,
    # subscription state or credential readiness changes the signature and
    # triggers another idempotent convergence pass.
    assert "_last_topology_signature" in runtime
    assert "signature != _last_topology_signature" in runtime
    assert "_last_topology_signature = _topology_signature()" in runtime
    assert "_converged_node_ids" not in runtime

    # Classic protocols keep the established idempotent autosync path.
    assert "sync_installed_node_to_subscriptions" in runtime
    assert "await sync_installed_node_to_subscriptions(db, node)" in runtime

    # Modern protocols are additive, entitlement-aware and only use real online
    # NodeProtocolConfig runtimes. Existing usable items are merged back after
    # the canonical modern provisioner creates a missing node item.
    assert "MODERN_PROTOCOL_KEYS" in runtime
    assert "plan_protocols" in runtime
    assert "selected & allowed & eligible_protocols" in runtime
    assert "_provision_modern_protocol" in runtime
    assert "[node]" in runtime
    assert "kept_items + list(new_items)" in runtime
    assert "_delivery_item_is_usable" in runtime

    # Failure does not advance the signature, so the same topology is retried.
    assert "if result.get(\"ok\")" in runtime
    assert "await asyncio.sleep(_RETRY_INTERVAL_SECONDS)" in runtime
    assert 'add_event_handler("startup", _startup)' in runtime
    assert 'add_event_handler("shutdown", _shutdown)' in runtime

    # Outer-loop failures identify the failing stage without logging secrets.
    assert 'stage = "topology_signature"' in runtime
    assert 'stage = "reconcile"' in runtime
    assert 'stage = "post_reconcile_signature"' in runtime
    assert 'f"stage={stage}"' in runtime

    # Logging remains summary-only; SSH details and decrypted credential payloads
    # are not emitted by the convergence worker.
    assert '"failed_count": len(classic_failed) + len(modern_failed)' in runtime
    assert '"error_type": type(exc).__name__' in runtime
    assert 'str(exc)' not in runtime

    assert "apply_node_subscription_convergence_v114" in composition
    assert "apply_node_subscription_convergence_v114()" in composition


def test_fresh_l2tp_install_requires_v113_ppp_telemetry_hooks():
    l2tp = _text("backend/app/l2tp_ppp_convergence_v111.py")
    dataplane = _text("backend/app/protocol_dataplane_desired_state_v87.py")
    main = _text("backend/app/main.py")

    assert 'TELEMETRY_MARKER = "TWINPANEL_L2TP_QUOTA_TELEMETRY_V113"' in l2tp
    assert 'TELEMETRY_UP_HOOK = "/etc/ppp/ip-up.d/twinpanel-l2tp-telemetry"' in l2tp
    assert 'TELEMETRY_DOWN_HOOK = "/etc/ppp/ip-down.d/twinpanel-l2tp-telemetry"' in l2tp
    assert "await _ensure_l2tp_telemetry_hooks(conn)" in l2tp
    assert "test -x {shlex.quote(TELEMETRY_UP_HOOK)}" in l2tp
    assert "test -x {shlex.quote(TELEMETRY_DOWN_HOOK)}" in l2tp
    assert "provision.install_l2tp = _install_l2tp_v111" in l2tp

    # The wrapper is part of the self-hosted runtime composition before API
    # requests can execute /v1/provision/install.
    assert "apply_l2tp_ppp_convergence_v111()" in dataplane
    assert "apply_self_hosted_runtime()" in main
