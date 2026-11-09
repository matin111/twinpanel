"""Per-node Sudoku whitelist ACK contract: no dependence on failed other families."""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import patch

from app.services import central_sudoku_fingerprint_v1 as fp


def test_order_independent_node_scoped_digest():
    assert fp.fingerprint_for_ids(19,[5,2,5,8])==fp.fingerprint_for_ids(19,[8,5,2])
    assert fp.fingerprint_for_ids(19,[2])!=fp.fingerprint_for_ids(22,[2])
    assert fp.fingerprint_for_ids(19,[2])!=fp.fingerprint_for_ids(19,[2,3])
    assert len(fp.fingerprint_for_ids(19,[]))==64


def test_invalid_subscription_fails_closed():
    for value in [-1,0]:
        try: fp.fingerprint_for_ids(19,[value])
        except ValueError: pass
        else: raise AssertionError("invalid identity allowed")


def test_independent_marker_isolation():
    written={}
    with patch.object(fp,"get_value",side_effect=lambda db,k,default:written.get(k,default)), \
         patch.object(fp,"set_value",side_effect=lambda db,k,v:written.__setitem__(k,v)):
        a=fp.fingerprint_for_ids(19,[1,2])
        fp.mark_applied(None,19,a)
        assert fp.last_applied(None,19)==a
        assert fp.last_applied(None,22)==""
        assert fp.marker_key(19)=="vpn.central_runtime.exit.19.sudoku.last_applied"


def test_delta_scheduler_is_isolated_from_global_runtime_failures():
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/"scripts/twinpanel_central_node_stage_v1.py"
    source=path.read_text(encoding="utf-8")
    assert "last_sudoku_applied(db,node_id)" in source
    assert "desired_sudoku_fingerprint(db,node_id)" in source
    assert 'if sudoku not in selected:' in source


def test_apply_marker_occurs_only_after_verified_sudoku_runtime():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"scripts/twinpanel_central_sudoku_shared_v2.py").read_text()
    assert "mark_sudoku_applied(db,node_id,sudoku_fingerprint_for_ids(node_id,ids))" in source
    assert source.index('ack=await apply(conn,all_accounts)') < source.index(
        'mark_sudoku_applied(db,node_id,sudoku_fingerprint_for_ids(node_id,ids))'
    )
    assert "SUDOKU_SHARED_ENTITLEMENTS_CHANGED_BEFORE_ACK" in source
    assert "SUDOKU_SHARED_DISABLED_EMPTY_WHITELIST" in source
    assert source.index('ack = await deactivate(conn)') < source.index(
        "mark_sudoku_applied(db, node_id, sudoku_fingerprint_for_ids(node_id, ()))"
    )


if __name__=="__main__":
    for name,test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):test()
    print("CENTRAL_SUDOKU_FINGERPRINT_V1_SMOKE_OK")
