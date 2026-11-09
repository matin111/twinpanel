"""Per-family Sudoku entitlement digest contract (no live server or DB writes)."""
from __future__ import annotations

from app.services.central_sudoku_fingerprint_v1 import fingerprint, sudoku_applied_key
from app.services import central_sudoku_fingerprint_v1 as subject
from unittest.mock import patch


def test_digest_ignores_account_order_and_duplicates():
    a=fingerprint(19, [4,2,3,2])
    b=fingerprint(19, [2,3,4])
    assert a==b and len(a)==64
    assert a!=fingerprint(22,[2,3,4])


def test_digest_changes_when_user_revoked_or_newly_entitled():
    a=fingerprint(19,[10,11,12])
    assert a!=fingerprint(19,[10,11])
    assert a!=fingerprint(19,[10,11,12,13])


def test_zero_entitlements_are_versioned_not_blank_or_global():
    digest=fingerprint(19,[])
    assert len(digest)==64
    assert sudoku_applied_key(19)=="vpn.central_runtime.exit.19.sudoku_whitelist_applied_v1"


def test_invalid_id_fail_closed():
    for ids in ((-1,), (0,),):
        try:
            fingerprint(19,ids)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid subscriber was accepted")
    try:
        fingerprint(0,[12])
    except ValueError:
        pass
    else:
        raise AssertionError("invalid node accepted")


def test_mark_is_same_derived_digest_and_has_no_implicit_commit():
    called=[]
    with patch.object(subject,"set_value",side_effect=lambda db,key,val:called.append((key,val))):
        value=subject.mark_applied(object(),19,[2,4,3])
    assert value==fingerprint(19,[3,2,4])
    assert called==[(sudoku_applied_key(19),value)]


def test_last_applied_is_a_read_only_setting():
    with patch.object(subject,"get_value",return_value="z"*64) as get:
        val=subject.last_applied(object(),19)
    assert val=="z"*64
    assert get.call_count==1


if __name__=="__main__":
    for name,fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("CENTRAL_SUDOKU_INDEPENDENT_FINGERPRINT_V1_OK")
