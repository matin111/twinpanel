from __future__ import annotations

import importlib.util
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def load_telemetry():
    path = APP / "amneziawg_live_telemetry_v221.py"
    spec = importlib.util.spec_from_file_location("tp_awg_live_v221", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    egress = (APP / "amneziawg_egress_v221.py").read_text(encoding="utf-8")
    delivery = (APP / "routers" / "modern_account_delivery_v1.py").read_text(encoding="utf-8")
    reconcile = (APP / "routers" / "modern_legacy_reconcile_v1.py").read_text(encoding="utf-8")
    live = (APP / "routers" / "public_connection_live_v4.py").read_text(encoding="utf-8")

    # Data-plane contract: managed egress must be durable, idempotent and scoped
    # only to the standalone AmneziaWG client pool.
    assert 'AMNEZIAWG_SUBNET = "10.254.0.0/16"' in egress
    assert 'AMNEZIAWG_INTERFACE = "tpawg0"' in egress
    assert "EGRESS_CONTRACT = 221" in egress
    assert "iptables -w 10" in egress
    assert "MASQUERADE" in egress
    assert 'FORWARD -i "$IFACE" -o "$EGRESS"' in egress
    assert 'FORWARD -i "$EGRESS" -o "$IFACE"' in egress
    assert "RELATED,ESTABLISHED" in egress
    assert "TwinPanel-AmneziaWG-Egress" in egress
    assert "twinpanel-amneziawg-egress.service" in egress
    assert "systemctl enable" in egress and "systemctl restart" in egress

    # Every successful account apply installs egress before persisting the item
    # and stamps the durable contract marker used by legacy self-heal.
    assert "ensure_amneziawg_egress" in delivery
    assert 'if protocol == "amneziawg"' in delivery
    assert 'item["egress_contract"] = int(egress["contract"])' in delivery

    # Existing complete credentials from rc.220 must be repaired once without
    # regenerating their stored standalone identity.
    assert '"legacy_amneziawg_egress"' in reconcile
    assert 'protocol not in {"naive", "amneziawg"}' in reconcile
    assert 'item.get("egress_contract")' in reconcile
    assert "EGRESS_CONTRACT" in reconcile
    assert "_LEGACY_REPAIR_STATES" in reconcile

    # Public Sublink telemetry must consume native AmneziaWG handshake/counters
    # and map the protocol card instead of relying only on Quota tables.
    assert "subscription_amneziawg_live" in live
    assert 'online_protocols.add("amneziawg")' in live
    assert "text.includes('amneziawg')" in live

    telemetry = load_telemetry()
    now = int(time.time())
    fresh = (
        "server-private\tserver-public\t8452\toff\n"
        f"client-public\t(none)\t198.51.100.2:50000\t10.254.0.18/32\t{now - 10}\t1200\t900\t25\n"
    )
    peers = telemetry.parse_amneziawg_dump(fresh, now_epoch=now)
    assert "10.254.0.18" in peers
    assert telemetry.peer_is_live(peers["10.254.0.18"]) is True

    stale = (
        "server-private\tserver-public\t8452\toff\n"
        f"client-public\t(none)\t198.51.100.2:50000\t10.254.0.18/32\t{now - 400}\t1200\t900\t25\n"
    )
    stale_peers = telemetry.parse_amneziawg_dump(stale, now_epoch=now)
    assert telemetry.peer_is_live(stale_peers["10.254.0.18"]) is False

    zero = (
        "server-private\tserver-public\t8452\toff\n"
        f"client-public\t(none)\t198.51.100.2:50000\t10.254.0.18/32\t{now - 10}\t0\t0\t25\n"
    )
    zero_peers = telemetry.parse_amneziawg_dump(zero, now_epoch=now)
    assert telemetry.peer_is_live(zero_peers["10.254.0.18"]) is False

    assert telemetry._client_ip("[Interface]\nAddress = 10.254.0.18/32\n") == "10.254.0.18"

    print("AMNEZIAWG_EGRESS=PASS")
    print("AMNEZIAWG_LEGACY_SELF_HEAL=PASS")
    print("AMNEZIAWG_NATIVE_LIVE=PASS")
    print("AMNEZIAWG_UI_MAPPING=PASS")


if __name__ == "__main__":
    main()
