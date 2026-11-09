"""Pure regression of remote sing-box identity collision-safe staging."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.services.central_singbox_idempotent_v1 import (
    resolve_remote_identity_collisions,
)
from app.singbox_subscription_accounts import (
    SingBoxAccountSecret, _user_record,
)


def make(protocol, name="tp-sub-1"):
    return SingBoxAccountSecret(
        protocol=protocol,username=name,password="new-pinned-password",
        uuid="4c1cd20c-e423-43bd-8ccf-d1e67cae128c" if protocol=="tuic" else None,
        userkey="new-user-key" if protocol=="snell" else None,
    )


def test_four_conflicts_are_aliased_without_overwriting_existing_customers():
    protocols=("anytls","hysteria2","snell","tuic")
    work=[(1,p,make(p)) for p in protocols]
    current={p:[_user_record(replace(make(p),password="old-different-password",
                                     userkey="old-key" if p=="snell" else make(p).userkey))]
             for p in protocols}
    old_snapshot={p:[dict(x) for x in rows] for p,rows in current.items()}
    resolved,stats=resolve_remote_identity_collisions(work,current,19)
    assert stats["alias_on_conflict"]==4
    assert all(s.username.startswith("tp-central-1-") for _,p,s in resolved)
    assert len(set(s.username for _,p,s in resolved))==4
    assert current==old_snapshot
    assert [s.password for _,p,s in resolved]==["new-pinned-password"]*4


def test_repeated_attempt_preserves_node_alias_and_canonical_secret():
    work=[(7,"anytls",make("anytls","tp-sub-7"))]
    inbound={"anytls":[_user_record(replace(work[0][2],password="prior-secret"))]}
    first,counts=resolve_remote_identity_collisions(work,inbound,22)
    second,repeat=resolve_remote_identity_collisions(work,inbound,22)
    assert first==second
    assert counts==repeat=={"alias_on_conflict":1}
    # A credential rotation uses a new alias rather than overwriting old.
    rotated=[(7,"anytls",replace(work[0][2],password="rotated-canonical"))]
    fresh,_=resolve_remote_identity_collisions(rotated,inbound,22)
    assert fresh[0][2].username!=first[0][2].username


def test_matching_existing_credentials_reused_unmodified():
    work=[(71,"naive",make("naive"))]
    inbound={"naive":[_user_record(work[0][2])]}
    resolved,counts=resolve_remote_identity_collisions(work,inbound,19)
    assert resolved==work
    assert counts=={"reused_identical":1}


def test_fresh_user_is_not_unnecessarily_aliased():
    work=[(71,"socks5",make("socks5"))]
    resolved,counts=resolve_remote_identity_collisions(work,{"socks5":[]},19)
    assert resolved==work
    assert counts=={"new_identity":1}


def test_alias_mismatch_fails_closed():
    secret=make("anytls")
    canonical=_user_record(replace(secret,password="prior-secret"))
    baseline=[(1,"anytls",secret)]
    alias,_=resolve_remote_identity_collisions(baseline,{"anytls":[canonical]},19)
    conflict=_user_record(replace(alias[0][2],password="unrelated-alias-password"))
    try:
        resolve_remote_identity_collisions(
            baseline,{"anytls":[canonical,conflict]},19
        )
    except RuntimeError as exc:
        assert str(exc)=="CENTRAL_SINGBOX_NODE_ALIAS_CONFLICT"
    else:
        raise AssertionError("alias collision unexpectedly replaced existing user")


def test_duplicate_remote_username_fails_closed():
    record=_user_record(make("anytls"))
    try:
        resolve_remote_identity_collisions(
            [(1,"anytls",make("anytls"))],{"anytls":[record,record]},19
        )
    except RuntimeError as exc:
        assert str(exc)=="CENTRAL_SINGBOX_REMOTE_DUPLICATE_USER"
    else:
        raise AssertionError("duplicate remote username silently accepted")


def test_canonical_persist_is_before_network_apply():
    script=(Path(__file__).resolve().parents[1]/
            "scripts/twinpanel_central_singbox_node_bulk_v1.py").read_text()
    assert "CENTRAL_SINGBOX_IDENTITY_PLAN" in script
    assert "row.secret_encrypted=ad._enc(secret_to_dict(secret))" in script
    assert script.index("row.secret_encrypted=ad._enc(secret_to_dict(secret))") < script.index(
        "confirmed=await apply_bulk("
    )
    assert "resolve_remote_identity_collisions(" in script
    assert script.index("resolve_remote_identity_collisions(") < script.index(
        "confirmed=await apply_bulk("
    )


if __name__=="__main__":
    for name,check in sorted(globals().items()):
        if name.startswith("test_") and callable(check):
            check()
    print("CENTRAL_SINGBOX_IDEMPOTENT_COLLISIONS_V1_OK")
