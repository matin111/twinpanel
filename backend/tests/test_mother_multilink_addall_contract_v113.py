from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(rel:str)->str:
    return (ROOT/rel).read_text(encoding="utf-8")

def test_mother_contract_is_separated():
    src=read("app/mother_subscription_delivery_policy_v108.py")
    stored=src.split("def _stored_info_with_mother_policy",1)[1].split("def _install_multilink_filter",1)[0]
    multi=src.split("def _install_multilink_filter",1)[1].split("def apply_mother_subscription_delivery_policy_v108",1)[0]
    assert "_subscription_can_use_mother(db, sub)" in stored
    assert "_filter_mother_from_delivery(db, payload)" in stored
    assert "_subscription_can_use_mother" not in multi
    assert "return sub, _filter_mother_from_delivery(db, payload)" in multi
    assert "account_delivery._stored_info = _stored_info_with_mother_policy" in src

def test_mother_identity_is_editable_without_affecting_provisioning():
    src=read("app/routers/mother_access.py")
    assert 'Node.agent_url == "local://core"' in src
    assert "mother_name: str | None = None" in src
    assert "public_domain: str | None = None" in src
    assert "mother.name = name" in src
    assert "mother.public_domain = _normalize_public_domain(payload.public_domain) or None" in src
    assert '"removed_mother_memberships": 0' in src

def test_legacy_add_all_never_injects_panel_name():
    src=read("app/routers/public_connection_protocol_subscriptions_v30.py")
    assert 'profile_title = f"{_account_name(sub)}-{normalized}"' in src
    assert '"Profile-Title": profile_title' in src
    assert "TwinPanel-" not in src
    assert "'TwinPanel '+title" not in src
