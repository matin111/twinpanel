from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT / "app" / "routers" / "modern_account_delivery_v1.py"
ENFORCEMENT = ROOT / "app" / "services" / "modern_enforcement_v1.py"
QUOTA_SYNC = ROOT / "app" / "services" / "quota_node_sync.py"
SINGBOX = ROOT / "app" / "singbox_subscription_accounts.py"


def test_naive_shadowtls_use_subscription_credentials_only():
    source = DELIVERY.read_text(encoding="utf-8")

    assert 'SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS = frozenset({"naive", "shadowtls"})' in source
    assert "username = str(sub.account_username or \"\").strip()" in source
    assert "password = str(sub.account_password_encrypted or \"\")" in source
    assert "SingBoxAccountSecret(" in source
    assert "sub.account_password_encrypted = password" in source


def test_legacy_identity_is_removed_during_binding_or_username_rotation():
    source = DELIVERY.read_text(encoding="utf-8")

    assert "previous_secret = _stored_singbox_secret(ad, cred, protocol)" in source
    assert "previous_username != current_username" in source
    assert "await _remove_singbox_identity(" in source
    assert "_mutation_script(protocol, username, None)" in source


def test_revoke_targets_stored_naive_shadowtls_identity():
    source = ENFORCEMENT.read_text(encoding="utf-8")

    assert 'SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS = frozenset({"naive", "shadowtls"})' in source
    assert "username = str(getattr(secret, \"username\", \"\") or \"\").strip()" in source
    assert "_mutation_script(protocol, username, None)" in source
    assert "await remove_account(conn, protocol, subscription_id)" in source


def test_accounting_uses_provisioned_runtime_identity():
    source = QUOTA_SYNC.read_text(encoding="utf-8")

    assert 'item.get("telemetry_identity")' in source
    assert 'item.get("username")' in source
    assert 'getattr(credential, "username", None)' in source


def test_shadowtls_inner_password_remains_node_runtime_state():
    source = SINGBOX.read_text(encoding="utf-8")

    assert 'seed.setdefault("inner_password", secrets.token_urlsafe(32))' in source
    assert "Inner proxy auth is node runtime state" in source
