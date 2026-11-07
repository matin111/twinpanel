"""Ensure modern Xray V47 repair can call the V39 TLS account adapter."""
import asyncio
from app import xray_tcp_tls_v39 as tls


def test_v39_forwards_reusable_connection(monkeypatch):
    seen = {}
    async def underlying(db, node, sub, user, client_id, *, reusable_connection=None):
        seen["conn"] = reusable_connection
        seen["id"] = client_id
        return {"profiles": []}
    monkeypatch.setattr(tls, "_original_xray_account_modern", underlying)
    connection = object()
    out = asyncio.run(tls._xray_account_modern_v39(
        object(), object(), object(), object(), "customer-uuid",
        reusable_connection=connection,
    ))
    assert out == {"profiles": []}
    assert seen == {"conn": connection, "id": "customer-uuid"}


def test_v39_backward_compatible_without_reusable_connection(monkeypatch):
    async def underlying(db, node, sub, user, client_id, *, reusable_connection=None):
        assert reusable_connection is None
        return {"profiles": []}
    monkeypatch.setattr(tls, "_original_xray_account_modern", underlying)
    out = asyncio.run(tls._xray_account_modern_v39(
        object(), object(), object(), object(), "customer-uuid"
    ))
    assert out == {"profiles": []}
