from pathlib import Path


def _source() -> str:
    return Path("backend/app/routers/modern_account_delivery_v1.py").read_text(encoding="utf-8")


def test_account_delivery_does_not_filter_nodes_to_exit_only():
    source = _source()

    assert "NodeType.EXIT" not in source
    assert "from ..models import (\n    Node,\n    NodeProtocolConfig,\n    NodeType," not in source
    assert "for node in ad._nodes(db, sub)" in source


def test_every_protocol_gets_its_own_timeout_without_shared_deadline():
    source = _source()

    assert "TOTAL_PROVISION_TIMEOUT_SECONDS" not in source
    assert "deadline =" not in source
    assert "remaining = deadline" not in source
    assert "break" not in source[source.index("for protocol in protocols:"):source.index("db.commit()")]
    assert "timeout = max(1.0, float(protocol_timeout))" in source


def test_skipped_servers_are_reported_instead_of_silently_disappearing():
    source = _source()

    assert '"error": "Protocol runtime is not online on this server"' in source
    assert '"error": "Protocol is not enabled on this server"' in source
