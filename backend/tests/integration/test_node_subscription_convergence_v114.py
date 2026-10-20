from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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


def test_failed_or_partial_exit_sync_gets_safe_background_retry():
    runtime = _text("backend/app/node_subscription_convergence_v114.py")
    composition = _text("backend/app/self_hosted_runtime.py")

    assert "TWINPANEL_NODE_SUBSCRIPTION_CONVERGENCE_V114" in runtime
    assert "Node.retired_at.is_(None)" in runtime
    assert "Node.node_type == NodeType.EXIT" in runtime
    assert "NodeAccess.created_at" in runtime
    assert "_NEW_ACCESS_GRACE_SECONDS = 180" in runtime
    assert "sync_installed_node_to_subscriptions" in runtime
    assert 'if ok:' in runtime
    assert "_converged_node_ids.add" in runtime
    assert "await asyncio.sleep(_RETRY_INTERVAL_SECONDS)" in runtime
    assert 'add_event_handler("startup", _startup)' in runtime
    assert 'add_event_handler("shutdown", _shutdown)' in runtime

    # Logging is deliberately summary-only; credential/SSH payloads are never
    # emitted by the convergence worker.
    assert '"failed_count": failed_count' in runtime
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
