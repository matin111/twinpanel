"""Shared Sudoku entitlement-removal and empty-whitelist safety regressions."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.central_sudoku_shared_runtime_v2 import (
    deactivate, remote_source, users_manifest,
)
from scripts import twinpanel_central_node_stage_v1 as stage


class FakeDB:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def get(self, model, node_id):
        return SimpleNamespace(id=int(node_id))


def missing(*, current: str, applied: str, audit: dict):
    state=SimpleNamespace(fingerprint=current)
    with patch.object(stage,"SessionLocal",return_value=FakeDB()), \
         patch.object(stage,"allow_central_node",return_value=True), \
         patch.object(stage,"load_desired_state",return_value=state), \
         patch.object(stage,"require_valid_desired_state",side_effect=lambda x,max_users:x), \
         patch.object(stage,"verify_coverage",return_value=audit), \
         patch.object(stage,"desired_sudoku_fingerprint",return_value=current), \
         patch.object(stage,"last_sudoku_applied",return_value=applied):
        return stage.missing_runtime_families(19,3000)


def okay_audit():
    return {
        "ok":True,
        "missing_by_protocol":{},
        "subscriptions_without_entitlements":[],
        "unknown_protocols":[],
        "missing_node_memberships":[],
    }


def test_revocation_reconciles_shared_daemon_even_when_all_remaining_creds_exist():
    selected=missing(current="a"*64,applied="b"*64,audit=okay_audit())
    assert [family.name for family in selected]==["sudoku"]


def test_unchanged_fingerprint_does_not_unnecessarily_restart_shared_daemon():
    selected=missing(current="a"*64,applied="a"*64,audit=okay_audit())
    assert selected==()


def test_failed_singbox_and_new_revocation_both_get_family_reconcile():
    audit=okay_audit()
    audit["ok"]=False
    audit["missing_by_protocol"]={"naive":3}
    selected=missing(current="a"*64,applied="b"*64,audit=audit)
    assert [family.name for family in selected]==["singbox","sudoku"]


def test_non_sudoku_global_fingerprint_changes_do_not_reapply_sudoku():
    # A failing Sing-box adapter cannot force redundant Sudoku restarts:
    # only the fully acknowledged Sudoku family fingerprint matters.
    assert missing(current="a"*64,applied="a"*64,audit=okay_audit())==()


def test_live_ack_is_written_only_after_native_confirmation():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/
          "scripts/twinpanel_central_sudoku_shared_v2.py").read_text()
    assert "mark_sudoku_applied(db, node_id, ids)" in text
    assert text.index("if ack[\"users\"]!=len(ids):") < text.index(
        "mark_sudoku_applied(db, node_id, ids)"
    )
    assert text.index("db.commit()\n        print(\"SUDOKU_SHARED_COMPLETE\"") > text.index(
        "mark_sudoku_applied(db, node_id, ids)"
    )
    assert "mark_sudoku_applied(db, node_id, ())" in text
    assert text.index('if not ack.get("deactivated"):') < text.index(
        "mark_sudoku_applied(db, node_id, ())"
    )


def test_live_daemon_ack_requires_exact_identity_set_not_only_count():
    src=remote_source()
    assert 'live_names==desired_names' in src
    assert 'len(live_users)==len(desired_names)' in src
    assert 'snapshot["count"]==len(clean)' in src
    assert 'verified=snapshot.get("count")==len(clean)' not in src


def test_empty_users_never_create_unrestricted_listener():
    try:
        users_manifest([])
    except ValueError as exc:
        assert "SUDOKU_SHARED_INVALID_USERS" in str(exc)
    else:
        raise AssertionError("empty whitelist was allowed into a running daemon")


def test_empty_staging_stops_only_owned_shared_service():
    src=remote_source()
    assert 'if action=="deactivate":' in src
    assert "SUDOKU_SHARED_UNIT_OWNERSHIP_CONFLICT" in src
    assert '["systemctl","disable","--now",SERVICE]' in src
    assert '["systemctl","is-enabled","--quiet",SERVICE]' in src
    # A stale live whitelist must not reappear from systemd on reboot.
    assert '["systemctl","stop",SERVICE]' not in src
    assert '"users":0,"port":PORT,"deactivated":True' in src
    assert "systemctl stop twinpanel-api" not in src
    assert "twinpanel-sudoku-sub-" not in src
    assert "SUDOKU_SHARED_DISABLED_EMPTY_WHITELIST" in (
        __import__("pathlib").Path(__file__).resolve().parents[1]/
        "scripts/twinpanel_central_sudoku_shared_v2.py"
    ).read_text(encoding="utf-8")


def test_deactivation_requires_remote_ack():
    import app.central_sudoku_shared_runtime_v2 as runtime
    class DummyConn: pass
    called=[]
    async def fake_remote(conn, request):
        called.append(request)
        return {"ok":True,"users":0,"deactivated":True}
    with patch.object(runtime,"_remote",side_effect=fake_remote):
        ack=asyncio.run(deactivate(DummyConn()))
        assert ack["deactivated"]
    assert called==[{"action":"deactivate"}]


if __name__=="__main__":
    for name,check in sorted(globals().items()):
        if name.startswith("test_") and callable(check):
            check()
    print("SUDOKU_CENTRAL_WHITELIST_REVOCATION_V1_OK")
