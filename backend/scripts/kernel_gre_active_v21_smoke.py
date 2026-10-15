from __future__ import annotations

import json
from types import SimpleNamespace

from app import transport_policy_v17 as v17
from app import transport_policy_v20 as v20
from app import tunnel_transport_manager_v7 as v7
from app.kernel_gre_agent_compat_v21 import patch_agent_source
from app.kernel_gre_auto_v21 import install_kernel_gre_active_v21
from app.routers import provision
from app.tp2027_transport import (
    TP2027_TRANSPORTS,
    tp2027_desired_meta,
    tp2027_interface_name,
)
from app.transport_candidates.common import runtime


class FakeQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.row


class FakeDB:
    def __init__(self, row):
        self.row = row

    def query(self, model):
        return FakeQuery(self.row)


def main() -> None:
    rt = runtime("kernel_gre", 5)

    assert rt["interface"] == "tpgr5"
    assert rt["network"] == "10.248.0.20/30"
    assert rt["iran_ip"] == "10.248.0.21"
    assert rt["exit_ip"] == "10.248.0.22"
    assert tp2027_interface_name("kernel_gre", 5) == "tpgr5"
    assert "kernel_gre" in TP2027_TRANSPORTS

    cfg = {
        **rt,
        "full_probe_ok": True,
        "mode": "gre-native",
    }

    row = SimpleNamespace(
        enabled=True,
        config_text=json.dumps(cfg),
    )

    tunnel = SimpleNamespace(
        id=5,
        active_transport="kernel_gre",
        iran_node_id=3,
        exit_node_id=2,
    )

    iran = tp2027_desired_meta(
        FakeDB(row),
        tunnel,
        3,
    )

    exit_node = tp2027_desired_meta(
        FakeDB(row),
        tunnel,
        2,
    )

    assert iran is not None
    assert exit_node is not None

    assert iran["interface"] == "tpgr5"
    assert iran["network"] == "10.248.0.20/30"
    assert iran["local_address"] == "10.248.0.21/30"
    assert iran["peer_tunnel_ip"] == "10.248.0.22"
    assert iran["exit_tunnel_ip"] == "10.248.0.22"
    assert iran["health_service"] == rt["iran_service"]

    assert exit_node["local_address"] == "10.248.0.22/30"
    assert exit_node["peer_tunnel_ip"] == "10.248.0.21"
    assert exit_node["health_service"] == rt["exit_service"]

    sample_agent = '''\n            managed_candidates = {\n                "quic_2027",\n                "backhaul",\n            }\n'''

    patched = patch_agent_source(sample_agent)
    assert '"kernel_gre"' in patched
    assert "TWINPANEL_AGENT_KERNEL_GRE_V21" in patched
    assert patch_agent_source(patched) == patched

    # tp2027_transport installs the shared make_agent hook at API import time.
    # Validate the exact rendered Agent source, not only the helper function.
    rendered_agent = provision.make_agent(
        999,
        "https://example.invalid",
    )
    assert '"kernel_gre"' in rendered_agent
    assert "TWINPANEL_AGENT_KERNEL_GRE_V21" in rendered_agent
    compile(
        rendered_agent,
        "<rendered-twinpanel-agent-v21>",
        "exec",
    )

    install_kernel_gre_active_v21()

    assert "kernel_gre" in v7.OVERLAY_NAMES
    assert "kernel_gre" in v7.SUPPORTED_NAMES
    assert "kernel_gre" in v17.MODERN_NAMES
    assert "kernel_gre" in v17.MANAGED_TRANSPORT_NAMES
    assert "kernel_gre" in v20.MODERN_NAMES
    assert "kernel_gre" in v20.ALL_NAMES
    assert v7.overlay_health_remote.__name__ == "kernel_gre_health_remote"

    print(
        "KERNEL_GRE_ACTIVE_V21_SMOKE_OK "
        "desired=tpgr5/10.248.0.20/30 manual=eligible auto=eligible agent=compatible"
    )


if __name__ == "__main__":
    main()
