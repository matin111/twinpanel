from __future__ import annotations

import inspect
from pathlib import Path

from app.services import accounting_device_map_batch_v1 as batch
from app.services import modern_quota_runtime_v257 as modern
from app.services import singbox_native_accounting_v265 as singbox


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source = inspect.getsource(batch.build_accounting_devices_by_node)
    cached = inspect.getsource(batch.build_node_devices_cached)
    installer = inspect.getsource(batch.install_accounting_device_batch_cache)
    worker = (ROOT / "scripts" / "twinpanel_modern_accounting_worker.py").read_text(
        encoding="utf-8"
    )

    # The performance invariant: active credentials, legacy node membership and
    # QuotaDevice rows are each bulk-loaded once for one reconcile Session.
    assert source.count("db.query(ProtocolCredential)") == 1
    assert "SubscriptionNode.subscription_id.in_(legacy_subscription_ids)" in source
    assert "QuotaDevice.subscription_id.in_(relevant_subscription_ids)" in source
    assert "canonical._decoded_credential_items(credential)" in source
    assert "decoded_by_credential" in source
    assert "seen_by_node" in source

    # The cache is explicitly Session-local. Both canonical accounting loops
    # create a fresh Session per reconcile pass, so nothing survives into the
    # next sweep and credential changes cannot be hidden across passes.
    assert "db.info.get(_CACHE_KEY)" in cached
    assert "db.info[_CACHE_KEY] = cache" in cached

    old_modern = modern.build_node_devices
    old_singbox = singbox.build_node_devices
    try:
        batch.install_accounting_device_batch_cache()
        assert modern.build_node_devices is batch.build_node_devices_cached
        assert singbox.build_node_devices is batch.build_node_devices_cached
    finally:
        modern.build_node_devices = old_modern
        singbox.build_node_devices = old_singbox

    # Wiring must happen before either long-lived accounting task starts.
    assert "install_accounting_device_batch_cache()" in worker
    assert worker.index("install_accounting_device_batch_cache()") < worker.index(
        "async def _serve()"
    )
    assert "ACCOUNTING_RECONCILE_INTERVAL_SECONDS = 15.0" in worker
    assert "modern_quota_runtime_loop()" in worker
    assert "singbox_native_accounting_loop()" in worker

    # No quota/accounting math, cadence, protocol collector or dataplane module
    # is replaced by this optimization; only the imported node-device builder is.
    assert "modern.build_node_devices = build_node_devices_cached" in installer
    assert "singbox.build_node_devices = build_node_devices_cached" in installer

    print("ACCOUNTING_DEVICE_MAP_BATCH_BULK_LOAD=PASS")
    print("ACCOUNTING_DEVICE_MAP_BATCH_SESSION_CACHE=PASS")
    print("ACCOUNTING_DEVICE_MAP_BATCH_WORKER_WIRING=PASS")


if __name__ == "__main__":
    main()
