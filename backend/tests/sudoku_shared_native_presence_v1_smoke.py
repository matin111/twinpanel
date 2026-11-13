"""Non-production contract checks for per-user Sudoku shared presence."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services import sudoku_shared_native_presence_v1 as subject


def snapshot(names, online):
    return subject.validate_snapshot({
        "marker": "TP_SUDOKU_SHARED_NATIVE_PRESENCE_V1",
        "names": names, "online": online,
        "total": len(names), "connections": sum(online.values()),
    })


def test_only_genuinely_connected_user_is_online_on_shared_port():
    data=snapshot(["tp-sub-11","tp-sub-22"],{"tp-sub-11":2})
    calls=[]
    def fake_presence(db, *, node_id, device, protocol, online, observed_at, client_ip, evidence):
        calls.append((int(device["subscription_id"]),online,protocol,evidence))
        return {"opened":int(online),"closed":int(not online)}
    with patch.object(subject.canonical,"_mark_presence",side_effect=fake_presence):
        result=subject.apply_shared_native_presence(
            object(),node=SimpleNamespace(id=19),
            devices=[{"subscription_id":11,"device_id":101},
                     {"subscription_id":22,"device_id":202}],
            snapshot=data,
        )
    assert [(v[0],v[1]) for v in calls]==[(11,True),(22,False)]
    assert result["online"]==1
    assert result["open_connections"]==2
    assert result["opened"]==1
    assert result["closed"]==1
    assert result["usage_events"]==0
    assert result["usage_supported"] is False
    assert result["matched"]==2


def test_no_connected_users_closes_stale_sessions_without_fake_online():
    data=snapshot(["tp-sub-11","tp-sub-22"],{})
    calls=[]
    def fake(db,*,node_id,device,protocol,online,observed_at,client_ip,evidence):
        calls.append(online)
        return {"opened":0,"closed":1}
    with patch.object(subject.canonical,"_mark_presence",side_effect=fake):
        result=subject.apply_shared_native_presence(
            object(),node=SimpleNamespace(id=22),
            devices=[{"subscription_id":11,"device_id":101},
                     {"subscription_id":22,"device_id":202}],snapshot=data)
    assert calls==[False,False]
    assert result["online"]==0
    assert result["closed"]==2


def test_missing_runtime_user_never_inherits_another_users_session():
    data=snapshot(["tp-sub-11"],{"tp-sub-11":3})
    calls=[]
    def fake(db,*,node_id,device,protocol,online,observed_at,client_ip,evidence):
        calls.append((device["subscription_id"],online))
        return {"opened":0,"closed":0}
    with patch.object(subject.canonical,"_mark_presence",side_effect=fake):
        stats=subject.apply_shared_native_presence(
            object(),node=SimpleNamespace(id=19),
            devices=[{"subscription_id":11,"device_id":11},
                     {"subscription_id":22,"device_id":22}],snapshot=data)
    assert calls==[(11,True),(22,False)]
    assert stats["matched"]==1


def test_malformed_unauthenticated_duplicate_and_truncated_snapshots_fail_closed():
    good={"marker":"TP_SUDOKU_SHARED_NATIVE_PRESENCE_V1","names":["tp-sub-1"],"online":{},"total":1,"connections":0}
    invalid=[
        {**good,"marker":"bad"},
        {**good,"names":["tp-sub-1","tp-sub-1"],"total":2},
        {**good,"online":{"tp-sub-2":1},"connections":1},
        {**good,"online":{"tp-sub-1":True},"connections":1},
        {**good,"online":{"tp-sub-1":2},"connections":1},
        {**good,"names":["test-user"]},
        {**good,"total":0},
        {**good,"names":"tp-sub-1"},
        {**good,"connections":-1},
        {**good,"total":3001},
    ]
    for payload in invalid:
        try:
            subject.validate_snapshot(payload)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid native Sudoku snapshot accepted")


def test_node_collector_is_local_authenticated_read_only():
    script=subject.node_collection_command()
    assert "http://127.0.0.1:19095/users" in script
    assert "secret" in script
    assert "SUDOKU_SHARED_CONTROLLER_CONFIG_MISMATCH" in script
    assert "systemctl" not in script
    assert "iptables" not in script
    assert "write_text" not in script
    assert "conn.run" not in script
    assert "client_key" not in script
    # Verified per-user cumulative wire counters are now part of this
    # authenticated read-only snapshot; passwords and client keys never are.
    assert "upTotal" in script and "downTotal" in script
    assert "InvocationID" in script
    assert "client_key" not in script


def test_async_ssh_success_and_error_never_expose_native_credentials():
    payload={"marker":"TP_SUDOKU_SHARED_NATIVE_PRESENCE_V1","names":["tp-sub-1"],
             "online":{"tp-sub-1":1},"total":1,"connections":1}
    class Conn:
        async def run(self, cmd, check, timeout):
            return SimpleNamespace(exit_status=0, stdout=json.dumps(payload))
    result=asyncio.run(subject.collect_shared_native_users(Conn()))
    assert result[0] is True
    assert result[1]["connections"]==1
    class FailingConn:
        async def run(self, cmd, check, timeout):
            return SimpleNamespace(exit_status=1,stderr="Bearer sensitive-secret",stdout="")
    failed=asyncio.run(subject.collect_shared_native_users(FailingConn()))
    assert failed[0] is False
    assert "sensitive" not in str(failed)


def test_dedicated_worker_retains_legacy_only_for_unregistered_exits():
    text=(Path(__file__).resolve().parents[1]/
          "scripts/twinpanel_sudoku_fast_presence_worker.py").read_text()
    assert "central_shared = is_central_node(db, node_id)" in text
    assert "if central_shared:" in text
    assert "collect_shared_native_users(conn)" in text
    assert "apply_shared_native_presence(" in text
    assert "canonical._collect_established_tcp_ports(conn)" in text
    assert "canonical._apply_sudoku_presence(" in text
    assert text.index("if central_shared:") < text.index(
        "canonical._collect_established_tcp_ports(conn)")
    # The two collector implementations must never run on the same node.
    assert "if central_shared:\n                    stats = apply_shared_native_presence" in text


if __name__=="__main__":
    for name,test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
    print("SUDOKU_SHARED_NATIVE_PRESENCE_V1_OK")

def test_validated_counters_are_exact_and_bounded():
    payload={"marker":"TP_SUDOKU_SHARED_NATIVE_PRESENCE_V1",
        "names":["tp-sub-11"],"online":{"tp-sub-11":1},
        "total":1,"connections":1,
        "epoch":"a"*32,
        "counters":{"tp-sub-11":{"up":300,"down":700}}}
    valid=subject.validate_snapshot(payload)
    assert valid["counters"]["tp-sub-11"]=={"up":300,"down":700}
    bad=[
        {**payload,"epoch":"bad"},
        {**payload,"counters":{"tp-sub-22":{"up":1,"down":2}}},
        {**payload,"counters":{"tp-sub-11":{"up":True,"down":2}}},
        {**payload,"counters":{"tp-sub-11":{"up":-1,"down":2}}},
        {**payload,"counters":{"tp-sub-11":{"up":3,"down":2**63}}},
    ]
    for row in bad:
        try: subject.validate_snapshot(row)
        except ValueError: pass
        else: raise AssertionError("unsafe Sudoku counter snapshot accepted")


def test_first_authoritative_snapshot_is_nonbillable_baseline():
    payload={"marker":"TP_SUDOKU_SHARED_NATIVE_PRESENCE_V1",
        "names":["tp-sub-11"],"online":{"tp-sub-11":1},
        "total":1,"connections":1,"epoch":"b"*32,
        "counters":{"tp-sub-11":{"up":300,"down":700}}}
    snapshot=subject.validate_snapshot(payload)
    calls=[]
    def fake_usage(db,**kwargs):
        calls.append(kwargs)
        return {"baselined":True,"event":False,"accepted_bytes":0}
    with patch.object(subject.canonical,"_active_sessions",return_value=[]),patch.object(
        subject.canonical,"_baseline_or_apply_cumulative",side_effect=fake_usage):
        row=subject.apply_shared_native_counters(
            object(),node=SimpleNamespace(id=29),
            devices=[{"subscription_id":11,"device_id":101}],snapshot=snapshot)
    assert row["usage_supported"] is True
    assert row["baselined"]==1 and row["accepted_bytes"]==0
    assert calls[0]["source_key"]=="sudoku:shared:11:"+"b"*32
    assert calls[0]["uplink"]==300 and calls[0]["downlink"]==700


def test_missing_authenticated_counters_cannot_charge_usage():
    seen=[]
    with patch.object(subject.canonical,"_baseline_or_apply_cumulative",side_effect=lambda *a,**k:seen.append(k)):
        row=subject.apply_shared_native_counters(
            object(),node=SimpleNamespace(id=29),
            devices=[{"subscription_id":11,"device_id":101}],
            snapshot=snapshot(["tp-sub-11"],{"tp-sub-11":1}))
    assert row["usage_supported"] is False
    assert seen==[]
