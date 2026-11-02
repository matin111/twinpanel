from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(rel:str)->str:
    return (ROOT/rel).read_text(encoding="utf-8")

def test_mother_contract_is_separated():
    src=read("app/mother_subscription_delivery_policy_v108.py")
    stored=src.split("def _stored_info_with_mother_policy",1)[1].split("def _refresh_delivery_node_names",1)[0]
    multi=src.split("def _install_multilink_full_payload",1)[1].split("def apply_mother_subscription_delivery_policy_v108",1)[0]
    assert "_subscription_can_use_mother(db, sub)" in stored
    assert "_filter_mother_from_delivery(db, payload)" in stored
    assert "_original_stored_info(db, sub)" in multi
    assert "_refresh_delivery_node_names(db, payload)" in multi
    assert "_filter_mother_from_delivery(db, payload)" not in multi
    assert "account_delivery._stored_info = _stored_info_with_mother_policy" in src

def test_mother_identity_is_editable_without_affecting_provisioning():
    src=read("app/routers/mother_access.py")
    assert 'Node.agent_url == "local://core"' in src
    assert "mother_name: str | None = None" in src
    assert "public_domain: str | None = None" in src
    assert "mother.name = name" in src
    assert "mother.public_domain = _normalize_public_domain(payload.public_domain) or None" in src
    assert '"removed_mother_memberships": 0' in src

def test_public_mother_label_uses_configured_node_name():
    src=read("app/routers/public_country_labels_runtime_v1.py")
    assert 'getattr(node, "name", "")' in src
    assert "_COUNTRY_LABELS_FA" not in src
    assert 'return "سرور مرکزی"' not in src

def test_add_all_deep_links_never_inject_panel_name():
    src=read("app/public_connect_import_identity_v1.py")
    assert "_HIDDIFY_OLD" in src
    assert "_KARING_OLD" in src
    assert "_HIDDIFY_NEW" in src
    assert "_KARING_NEW" in src
    assert "reference_v38._SCRIPT = _clean_script(reference_v38._SCRIPT)" in src

def test_legacy_add_all_never_injects_panel_name():
    src=read("app/routers/public_connection_protocol_subscriptions_v30.py")
    assert 'profile_title = f"{_account_name(sub)}-{normalized}"' in src
    assert '"Profile-Title": profile_title' in src
    assert "TwinPanel-" not in src
    assert "'TwinPanel '+title" not in src
