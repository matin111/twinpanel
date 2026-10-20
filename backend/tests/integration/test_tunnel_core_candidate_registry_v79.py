from __future__ import annotations

import inspect
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import unified_l3_agent_rollout_v49 as rollout  # noqa: E402
from app import unified_l3_candidate_registry_v79 as registry  # noqa: E402
from app import unified_l3_core_v49 as core  # noqa: E402
from app.transport_candidates import SPECS  # noqa: E402
from app.transport_candidates import common  # noqa: E402


def test_packet_loss_parser_and_probe_contract() -> None:
    assert common.parse_packet_loss_pct(
        "3 packets transmitted, 3 received, 0% packet loss, time 2001ms"
    ) == 0.0
    assert common.parse_packet_loss_pct(
        "3 packets transmitted, 2 received, 33.3333% packet loss, time 2001ms"
    ) == 33.3333
    assert common.parse_packet_loss_pct("no ping summary") is None

    source = inspect.getsource(common.probe)
    assert "LC_ALL=C ping" in source
    assert '"packet_loss_pct": packet_loss' in source
    assert '"iran_packet_loss_pct"' in source
    assert '"exit_packet_loss_pct"' in source
    assert "peer_ping_loss_parse_failed" in source


def test_unified_l3_uses_transport_candidate_registry() -> None:
    original_source = core._AGENT_RECONCILE_V49
    original_marker = rollout._AGENT_MARKER
    original_applied = registry._runtime_applied

    try:
        registry._runtime_applied = False
        registry.apply_unified_l3_candidate_registry_v79()

        rendered = core._AGENT_RECONCILE_V49
        assert registry.AGENT_MARKER in rendered
        assert rollout._AGENT_MARKER == registry.AGENT_MARKER

        for name in SPECS:
            assert repr(name) in rendered

        assert "managed_candidates.update(" in rendered
        assert 'selected == "mtunnel"' in rendered
        assert "or selected in" in rendered
        assert "unified_l3_carrier_probe(" in rendered

        # A second application must be byte-idempotent.
        once = rendered
        registry.apply_unified_l3_candidate_registry_v79()
        assert core._AGENT_RECONCILE_V49 == once
    finally:
        core._AGENT_RECONCILE_V49 = original_source
        rollout._AGENT_MARKER = original_marker
        registry._runtime_applied = original_applied


def test_agent_rollout_marker_is_dynamic() -> None:
    original_marker = rollout._AGENT_MARKER

    try:
        rollout._AGENT_MARKER = "TWINPANEL_TEST_DYNAMIC_MARKER"
        check = rollout._marker_probe_command()
        verify = rollout._marker_probe_command(verify_service=True)

        assert "TWINPANEL_TEST_DYNAMIC_MARKER" in check
        assert "TWINPANEL_TEST_DYNAMIC_MARKER" in verify
        assert "systemctl is-active --quiet twinpanel-agent.service" in verify
    finally:
        rollout._AGENT_MARKER = original_marker
