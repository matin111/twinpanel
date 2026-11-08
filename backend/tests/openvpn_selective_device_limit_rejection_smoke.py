"""Selective OpenVPN over-limit disconnect must never target an unrelated session."""
import asyncio
import ast
from types import SimpleNamespace

from app.services import openvpn_quota_runtime_v106 as mod


def main():
    original_collector = mod._collect_openvpn_sessions
    original_kill = mod._send_openvpn_client_kill_local
    original_ssh = mod.ssh_connect_saved
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
        # Remote node must use numeric CID and a syntactically valid script,
        # without ever passing a common name to OpenVPN management.
        scripts = []
        class FakeConn:
            async def run(self, script, *, check, timeout):
                scripts.append(script)
                assert check is False and timeout <= 8
                assert "client-kill 42" in script
                assert "kill mv7n2" not in script
                script_body = script.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
                ast.parse(script_body)
                return SimpleNamespace(exit_status=0, stdout="True\n")
            def close(self):
                pass
            async def wait_closed(self):
                pass
        async def fake_ssh(_node, _db):
            return FakeConn()
        mod.ssh_connect_saved = fake_ssh
        mod._collect_openvpn_sessions = fresh_same
        remote = SimpleNamespace(is_mother=False, agent_url="")
        result = asyncio.run(mod._disconnect_rejected_openvpn_sessions(remote, None, rejected))
        assert result == [{"client_id": 42, "ok": True}]
        assert len(scripts) == 1
        print("OPENVPN_SELECTIVE_LIMIT_REJECTION_PASS")
    finally:
        mod._collect_openvpn_sessions = original_collector
        mod._send_openvpn_client_kill_local = original_kill
        mod.ssh_connect_saved = original_ssh


if __name__ == "__main__":
    main()
