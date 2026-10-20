from __future__ import annotations

from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
HOOKS = BACKEND / "app" / "l2tp_ppp_convergence_v111.py"
COLLECTOR = BACKEND / "app" / "services" / "l2tp_quota_runtime_v113.py"
MAINTENANCE = BACKEND / "app" / "services" / "customer_maintenance.py"
QUOTA_SYNC = BACKEND / "app" / "services" / "quota_node_sync.py"


def main() -> None:
    hooks = HOOKS.read_text(encoding="utf-8")
    collector = COLLECTOR.read_text(encoding="utf-8")
    maintenance = MAINTENANCE.read_text(encoding="utf-8")
    quota_sync = QUOTA_SYNC.read_text(encoding="utf-8")

    # Production proof: a real PPP session existed on ppp0 with non-zero
    # counters while the L2TP quota ledger had zero sessions/events. Repair must
    # install fail-open hooks that record the authenticated PEERNAME and exact
    # pppd lifetime without sending HTTP from pppd itself.
    for token in (
        "TWINPANEL_L2TP_QUOTA_TELEMETRY_V113",
        "/etc/ppp/ip-up.d/twinpanel-l2tp-telemetry",
        "/etc/ppp/ip-down.d/twinpanel-l2tp-telemetry",
        "/run/twinpanel/l2tp-sessions",
        'PEER="${PEERNAME:-}"',
        '[ "$LOCAL_IP" = "10.94.0.1" ]',
        "10.94.0.*",
        "pppd_pid=%s",
        "chmod 755",
        "await _ensure_l2tp_telemetry_hooks(conn)",
    ):
        assert token in hooks, token

    assert "curl " not in hooks
    assert "http://" not in hooks
    assert "https://" not in hooks

    # A node that lacks telemetry hooks is intentionally not considered fully
    # repaired, so the preflight-safe V111 convergence path deploys them.
    assert "test -x" in hooks
    assert "grep -Fq" in hooks
    assert "quota_hooks" in hooks

    # The controller is the only quota writer. It reads authoritative live PPP
    # markers and kernel byte counters, maps CHAP username -> canonical L2TP
    # QuotaDevice, opens/touches sessions, emits cumulative usage and closes a
    # session only after a successful poll proves it disappeared.
    for token in (
        "reconcile_l2tp_quota_runtime_once",
        "L2TP_TELEMETRY_STATE_DIR",
        "/sys/class/net/{iface}/statistics",
        'counter("rx_bytes")',
        'counter("tx_bytes")',
        'item.get("protocol") or "") != "l2tp"',
        'protocol="l2tp"',
        'counter_mode="cumulative"',
        "open_session(",
        "apply_usage_event(",
        "close_session(",
        "if not ok:",
        "continue",
    ):
        assert token in collector, token

    failure_branch = collector.split("if not ok:", 1)[1].split("try:", 1)[0]
    assert "close_session(" not in failure_branch

    # L2TP already has a canonical quota identity in node config. For L2TP the
    # runtime identity is the credential username, which is the CHAP PEERNAME.
    assert '"l2tp": "l2tp"' in quota_sync
    assert "fallback_identity=identity" in quota_sync

    # The existing maintenance worker must run L2TP alongside Cisco/Xray and
    # OpenVPN rather than creating another independent daemon.
    assert "from .l2tp_quota_runtime_v113 import reconcile_l2tp_quota_runtime_once" in maintenance
    assert "l2tp_result = await reconcile_l2tp_quota_runtime_once()" in maintenance
    assert "l2tp quota runtime reconcile failed:" in maintenance

    print("L2TP_QUOTA_RUNTIME_V113_OK")


if __name__ == "__main__":
    main()
