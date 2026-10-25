from __future__ import annotations

from app import smart_transport_auto_v21 as smart
from app import transport_candidates as candidates
from app import tp27_reference_runtime_v91 as reference_v91
from app.kernel_transport_registry_v209 import apply_kernel_transport_registry_v209
from app.spoof_candidate_policy_v202 import apply_spoof_candidate_policy_v202


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

    policy_ids = {
        candidates.policy_ids("tp6_fast", 77)[0],
        candidates.policy_ids("kernel_ipip", 77)[0],
        candidates.policy_ids("kernel_vxlan", 77)[0],
    }
    assert len(policy_ids) == 3

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

    print(
        "KERNEL_TRANSPORT_V209_OK",
        "active=" + ",".join(sorted(expected)),
        "auto_install=" + ",".join(smart.AUTO_INSTALL_NAMES),
    )


if __name__ == "__main__":
    main()
