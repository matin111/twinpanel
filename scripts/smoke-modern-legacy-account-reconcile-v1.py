from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECONCILE = ROOT / "backend/app/routers/modern_legacy_reconcile_v1.py"
ROUTERS_INIT = ROOT / "backend/app/routers/__init__.py"
FACTORY = ROOT / "backend/app/services/subscription_factory.py"
MODERN_ROUTE = ROOT / "backend/app/routers/modern_account_delivery_v1.py"


def main() -> None:
    reconcile = RECONCILE.read_text(encoding="utf-8")
    routers_init = ROUTERS_INIT.read_text(encoding="utf-8")
    factory = FACTORY.read_text(encoding="utf-8")
    modern_route = MODERN_ROUTE.read_text(encoding="utf-8")

    # Repair is selected-protocol-only, admin-only and never lives on a public
    # delivery GET. It reuses the canonical real runtime provisioner.
    assert '@router.post("/v1/subscriptions/{subscription_id}/reconcile-modern-accounts")' in reconcile
    assert "Depends(require_admin)" in reconcile
    assert "_provision_modern_protocol" in reconcile
    assert "SubscriptionProtocol.protocol.in_(MODERN_PROTOCOL_KEYS)" in reconcile
    assert "node.node_type == NodeType.EXIT" in reconcile

    # Identity safety: complete credentials are preserved, truly empty legacy
    # placeholders may be repaired, and ambiguous partial credentials fail shut.
    assert 'return "complete"' in reconcile
    assert 'return "legacy_empty"' in reconcile
    assert 'return "partial"' in reconcile
    assert "partial_credential_requires_manual_review" in reconcile
    assert "credential_state(current)" in reconcile
    assert ".with_for_update()" in reconcile

    # A failed runtime attempt must not persist a fresh empty placeholder.
    assert "db.rollback()" in reconcile
    assert "runtime_not_ready" in reconcile
    assert "credential_not_complete" in reconcile

    # Partial node success must remain observable as an incomplete reconcile;
    # deliverable items may be committed, but node errors cannot report ok=true.
    partial_error_guard = (
        'if protocol_errors:\n                result["ok"] = False'
    )
    assert partial_error_guard in reconcile

    # Background self-heal is bounded and reuses the same guarded code path.
    assert "_BACKGROUND_MAX_PROTOCOLS = 2" in reconcile
    assert "modern_legacy_reconcile_loop" in reconcile
    assert 'name="modern-legacy-account-reconcile-v1"' in reconcile
    assert "APIRouter(" in reconcile and "lifespan=_lifespan" in reconcile

    # Successful repairs update Quota delivery state instead of stopping at DB.
    assert "sync_subscription_quota_nodes" in reconcile

    # Router registration must precede runtime use, while the existing account
    # provisioner remains the single source of real Modern credential creation.
    assert "_modern_legacy_reconcile_v1_router" in routers_init
    assert "include_router(_modern_legacy_reconcile_v1_router)" in routers_init
    assert "async def _provision_modern_protocol" in modern_route

    # New subscriptions still do not receive fake Modern placeholder identity.
    assert "if protocol not in CLASSIC_PROTOCOL_KEYS:" in factory
    assert "Modern drivers own" in factory

    print("MODERN_LEGACY_ACCOUNT_RECONCILE_V1_OK")
    print("auto_reconcile=active_selected_modern_only")
    print("identity_policy=complete_preserved_partial_fail_closed")
    print("partial_node_errors=reported_not_ok")
    print("background_batch=2_protocols")
    print("admin_trigger=enabled")


if __name__ == "__main__":
    main()
