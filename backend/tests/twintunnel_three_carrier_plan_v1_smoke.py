"""Rakhsh multiple carriers are independent of node count; no live cutover."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("carrier_plan",ROOT/"app/services/twintunnel_carrier_plan_v1.py")
mod=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)


def test_default_links_use_two_nodes_and_three_distinct_sockets():
    links=tuple(mod.Carrier(*row) for row in mod.DEFAULT_LINKS)
    assert mod.validate_links(links)==links
    args=mod.init_args("203.0.113.44",links)
    assert args==["rakhsh","init","--tunnel-addr","203.0.113.44:17443",
                 "--carrier","wss","--resume","--link","quicv2","--link","kcp:17001"]
    status=mod.planned_status()
    assert status["carrier_count"]==3
    assert status["carrier_state"]=="not_installed"
    assert status["traffic_activated"] is False


def test_conflicts_and_invalid_addresses_are_rejected():
    for links in (
        (mod.Carrier("tcp",17001),mod.Carrier("wss",17001),mod.Carrier("kcp",17002)),
        (mod.Carrier("wss",17001),mod.Carrier("quicv2",17001)),
        (mod.Carrier("wss",17001),mod.Carrier("quicv2",17001),mod.Carrier("kcp",17001),mod.Carrier("tcp",17002)),
    ):
        try: mod.validate_links(links)
        except ValueError: pass
        else: raise AssertionError("invalid links accepted")
    for ip in ("127.0.0.1","::1","not-an-ip"):
        try: mod.init_args(ip,tuple(mod.Carrier(*x) for x in mod.DEFAULT_LINKS))
        except ValueError: pass
        else: raise AssertionError("invalid peer accepted")


if __name__=="__main__":
    test_default_links_use_two_nodes_and_three_distinct_sockets()
    test_conflicts_and_invalid_addresses_are_rejected()
    print("TWINTUNNEL_THREE_CARRIER_PLAN_V1_SMOKE_OK")
