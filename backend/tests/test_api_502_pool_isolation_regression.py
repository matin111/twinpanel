"""Regression checks for customer API outage / PostgreSQL pool isolation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"


def test_http_dependencies_use_an_independent_bounded_pool():
    source = (ROOT / "database.py").read_text(encoding="utf-8")
    assert "request_engine = create_engine(" in source
    assert "RequestSessionLocal = sessionmaker(" in source
    assert "def get_db():\n    db = RequestSessionLocal()" in source
    assert "pool_size=10" in source
    assert "max_overflow=6" in source
    assert "pool_timeout=5" in source
    assert "pool_pre_ping=True" in source
    assert "connect_args=_DATABASE_CONNECT_ARGS" in source
    assert "db.close()" in source
    assert "SessionLocal = sessionmaker(" in source
    compile(source, "database.py", "exec")


def test_v2ray_alias_is_python_code_not_swallowed_in_comment():
    source = (ROOT / "routers" / "public_connection_protocol_subscriptions_v30.py").read_text(encoding="utf-8")
    assert '    if _normalize_protocol(protocol) == "v2ray":\n' in source
    assert "        from .public_connection_multilink_v7 import _subscription_response\n" in source
    assert "        return _subscription_response(token, db)\n" in source
    assert "    content, normalized, count = _protocol_subscription_content(token, protocol, db)\n" in source
    assert "\\n    # The legacy generic path" not in source
    compile(source, "public_connection_protocol_subscriptions_v30.py", "exec")
