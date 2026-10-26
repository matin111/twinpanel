from __future__ import annotations

from pathlib import Path

from app import smart_transport_auto_v21 as smart
from app import transport_candidates as candidates
from app import tp27_reference_runtime_v91 as reference_v91
from app.kernel_transport_registry_v209 import (
    KERNEL_IPIP_RULE_BASE,
    KERNEL_IPIP_TABLE_BASE,
    KERNEL_POLICY_SPAN,
    KERNEL_VXLAN_RULE_BASE,
    KERNEL_VXLAN_TABLE_BASE,
    LINUX_MAIN_RULE_PRIORITY,
    apply_kernel_transport_registry_v209,
)
from app.spoof_candidate_policy_v202 import apply_spoof_candidate_policy_v202
from app.tp6_candidate_registry_v208 import (
    TP6_POLICY_RULE_BASE,
    TP6_POLICY_SPAN,
    TP6_POLICY_TABLE_BASE,
)


def _source(relative: str) -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / relative).read_text(encoding="utf-8")


def main() -> None:
    apply_spoof_candidate_policy_v202()
    apply_kernel_transport_registry_v209()

    expected = {
        "tp27_fast",
        "spoof_wg",
        "tp6_fast",
        "kernel_ipip",
        "kernel_vxlan",
    }

    assert expected.issubset(set(candidates.ACTIVE_SPECS))
    assert expected.issubset({row["transport"] for row in candidates.catalog()})
    assert expected.issubset(set(smart.CANDIDATE_NAMES))
    assert expected.issubset(set(smart.ALL_AUTO_NAMES))

    # New kernel lanes are explicit-install only. The production automatic
    # installer authority must stay exactly on the proven TP27 lane.
    assert tuple(smart.AUTO_INSTALL_NAMES) == ("tp27_fast",)

    for name in ("tp6_fast", "kernel_ipip", "kernel_vxlan"):
        assert name in candidates.INSTALLERS
        assert callable(candidates.INSTALLERS[name])

    ipip = candidates.runtime("kernel_ipip", 77)
    vxlan = candidates.runtime("kernel_vxlan", 77)
    tp6 = candidates.runtime("tp6_fast", 77)

    assert ipip["transport"] == "kernel_ipip"
    assert vxlan["transport"] == "kernel_vxlan"
    assert tp6["transport"] == "tp6_fast"

    assert ipip["network"].startswith("10.244.")
    assert vxlan["network"].startswith("10.243.")
    assert tp6["network"].startswith("10.249.")
    assert len({ipip["network"], vxlan["network"], tp6["network"]}) == 3

    assert ipip["port"] is None
    assert 37000 <= int(vxlan["port"]) <= 37999

    # V211 regression: route-table IDs remain stable, while source-policy rule
    # priorities move ahead of Linux's built-in `main` rule at priority 32766.
    # The real Tunnel #6 VXLAN canary proved that the previous 36006 rule was
    # too late: `ip route get ... from 10.243.0.25` selected ens3 instead of
    # tpvx6, leaving the candidate NAT counter at zero.
    assert candidates.policy_ids("tp6_fast", 6) == (34006, 30006)
    assert candidates.policy_ids("kernel_ipip", 6) == (35006, 30906)
    assert candidates.policy_ids("kernel_vxlan", 6) == (36006, 31806)

    assert TP6_POLICY_SPAN == KERNEL_POLICY_SPAN == 900
    assert TP6_POLICY_TABLE_BASE == 34000
    assert KERNEL_IPIP_TABLE_BASE == 35000
    assert KERNEL_VXLAN_TABLE_BASE == 36000

    assert TP6_POLICY_RULE_BASE + TP6_POLICY_SPAN - 1 < KERNEL_IPIP_RULE_BASE
    assert KERNEL_IPIP_RULE_BASE + KERNEL_POLICY_SPAN - 1 < KERNEL_VXLAN_RULE_BASE
    assert KERNEL_VXLAN_RULE_BASE + KERNEL_POLICY_SPAN - 1 < LINUX_MAIN_RULE_PRIORITY

    for tunnel_id in (1, 6, 77, 899, 900, 1799):
        tp6_table, tp6_priority = candidates.policy_ids("tp6_fast", tunnel_id)
        ipip_table, ipip_priority = candidates.policy_ids("kernel_ipip", tunnel_id)
        vxlan_table, vxlan_priority = candidates.policy_ids("kernel_vxlan", tunnel_id)

        assert TP6_POLICY_TABLE_BASE <= tp6_table < TP6_POLICY_TABLE_BASE + 900
        assert KERNEL_IPIP_TABLE_BASE <= ipip_table < KERNEL_IPIP_TABLE_BASE + 900
        assert KERNEL_VXLAN_TABLE_BASE <= vxlan_table < KERNEL_VXLAN_TABLE_BASE + 900

        assert TP6_POLICY_RULE_BASE <= tp6_priority < TP6_POLICY_RULE_BASE + 900
        assert KERNEL_IPIP_RULE_BASE <= ipip_priority < KERNEL_IPIP_RULE_BASE + 900
        assert KERNEL_VXLAN_RULE_BASE <= vxlan_priority < KERNEL_VXLAN_RULE_BASE + 900

        assert tp6_priority < LINUX_MAIN_RULE_PRIORITY
        assert ipip_priority < LINUX_MAIN_RULE_PRIORITY
        assert vxlan_priority < LINUX_MAIN_RULE_PRIORITY
        assert len({tp6_priority, ipip_priority, vxlan_priority}) == 3

    # V210/V212 regression: a failed kernel canary must remove probe-owned
    # Iran policy state, Exit MASQUERADE state, and candidate-owned legacy
    # FORWARD residue, then verify all of those artifacts are absent. The
    # Tunnel #6 production audit found two historical VXLAN FORWARD rules after
    # interface/service/NAT cleanup; matching by exact candidate network and
    # exact TwinPanel comment keeps unrelated VPN protocol rules out of scope.
    cleanup = _source("app/transport_candidates/kernel_cleanup_v210.py")
    assert "while ip rule del priority" in cleanup
    assert "ip route flush table" in cleanup
    assert "iptables -t nat -D POSTROUTING" in cleanup
    assert "iptables -L FORWARD --line-numbers -n" in cleanup
    assert 'iptables -D FORWARD "$RULE_NO"' in cleanup
    assert 'awk -v net="$NETWORK" -v c="$COMMENT"' in cleanup
    assert "policy_rule_cleanup_failed" in cleanup
    assert "policy_table_cleanup_failed" in cleanup
    assert "canary_nat_cleanup_failed" in cleanup
    assert "canary_forward_cleanup_failed" in cleanup
    assert "exit_firewall_cleanup_rc=" in cleanup

    for relative in (
        "app/transport_candidates/kernel_ipip.py",
        "app/transport_candidates/kernel_vxlan.py",
    ):
        source = _source(relative)
        assert "from .kernel_cleanup_v210 import cleanup_probe_state" in source
        assert "cleanup_errors = await cleanup_probe_state(" in source
        assert 'cleanup_detail = "ok" if not cleanup_errors' in source
        assert "rm -f" in source
        assert "systemctl daemon-reload" in source
        assert "helper=_helper_path(tunnel_id" in source

    # V91 reapplies the V202 policy at reconciler startup. V209 must survive
    # that late refresh rather than disappearing after initial registration.
    reference_v91.activate_manager_candidate_policy_v91()
    assert "kernel_ipip" in smart.CANDIDATE_NAMES
    assert "kernel_vxlan" in smart.CANDIDATE_NAMES
    assert tuple(smart.AUTO_INSTALL_NAMES) == ("tp27_fast",)

    # API workers must load the same registry as the standalone manager.
    from app.routers.modern_transports import transport_catalog

    api_names = {
        row["transport"]
        for row in transport_catalog()["transports"]
    }
    assert expected.issubset(api_names)

    # V257 regression: manual production selection is no longer a DB-only
    # control-plane write. The endpoint must force a fresh full candidate probe,
    # wait for post-reconcile Agent reports from both peers, and roll aggregate
    # authority back if the new carrier/data plane is not accepted. Unified L3
    # remains the only service-route publisher; the API must not add direct
    # iptables/route mutation to the cutover path.
    modern = _source("app/routers/modern_transports.py")
    assert "TWINPANEL_MANUAL_CUTOVER_ACCEPTANCE_V257" in modern
    assert "async def select_modern_transport_manual(" in modern
    assert "smart._candidate_health_cache.pop(key, None)" in modern
    assert "await smart.candidate_health_remote_v21(" in modern
    assert "_wait_manual_cutover_acceptance_v257(" in modern
    assert "TunnelPeerState.node_id.in_(node_ids)" in modern
    assert 'item["fresh"]' in modern
    assert 'item["selected_transport"] == name' in modern
    assert "_rollback_manual_cutover_v257(" in modern
    assert '"rolled_back": True' in modern
    assert '"dataplane_reconciled": True' in modern
    assert "tunnel.last_switch_at = cutover_started_at" in modern

    cutover_start = modern.index("# TWINPANEL_MANUAL_CUTOVER_ACCEPTANCE_V257")
    cutover_source = modern[cutover_start:]
    assert "iptables " not in cutover_source
    assert "ip route " not in cutover_source

    print(
        "KERNEL_TRANSPORT_V257_OK",
        "active=" + ",".join(sorted(expected)),
        "auto_install=" + ",".join(smart.AUTO_INSTALL_NAMES),
        "failure_cleanup=policy,nat,legacy-forward,service,helper,unit",
        "policy_rules=tp6:300xx,ipip:309xx,vxlan:318xx",
        "manual_cutover=fresh-probe+dual-agent-acceptance+rollback",
        f"linux_main={LINUX_MAIN_RULE_PRIORITY}",
    )


if __name__ == "__main__":
    main()
