"""Selective OpenVPN over-limit disconnect must never target an unrelated session."""
import asyncio
from types import SimpleNamespace

from app.services import openvpn_quota_runtime_v106 as mod


def main():
    original_collector = mod._collect_openvpn_sessions
    original_kill = mod._send_openvpn_client_kill_local
    attempted = []

    try:
        async def fresh_same(_node, _db):
            return True, [{"client_id": 42, "identity": "mv7n2", "session_identity": "mv7n2:1234:42"}], None

        mod._collect_openvpn_sessions = fresh_same
        mod._send_openvpn_client_kill_local = lambda cid: attempted.append(cid) or True
        node = SimpleNamespace(is_mother=True, agent_url="local://core")
        rejected = [{"client_id": 42, "identity": "mv7n2", "session_identity": "mv7n2:1234:42"}]
        result = asyncio.run(mod._disconnect_rejected_openvpn_sessions(node, None, rejected))
        assert result == [{"client_id": 42, "ok": True}]
        assert attempted == [42]

        # A client ID is not stable across reconnects. Never kill if reused.
        async def changed(_node, _db):
            return True, [{"client_id": 42, "identity": "mv8n2", "session_identity": "mv8n2:9999:42"}], None
        mod._collect_openvpn_sessions = changed
        result = asyncio.run(mod._disconnect_rejected_openvpn_sessions(node, None, rejected))
        assert result == [{"client_id": 42, "ok": False, "reason": "session_changed"}]
        assert attempted == [42]

        # Telemetry failure must not trigger blind disconnection.
        async def unavailable(_node, _db):
            return False, [], "management_unavailable"
        mod._collect_openvpn_sessions = unavailable
        result = asyncio.run(mod._disconnect_rejected_openvpn_sessions(node, None, rejected))
        assert result[0]["reason"] == "recheck_unavailable"
        assert attempted == [42]
        print("OPENVPN_SELECTIVE_LIMIT_REJECTION_PASS")
    finally:
        mod._collect_openvpn_sessions = original_collector
        mod._send_openvpn_client_kill_local = original_kill


if __name__ == "__main__":
    main()
