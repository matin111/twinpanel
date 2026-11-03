from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "app"


def main() -> None:
    publish = (ROOT / "routers" / "publish_node_all_users_v2.py").read_text()
    lockfix = (ROOT / "routers" / "modern_legacy_reconcile_lockfix_v2.py").read_text()

    assert "_sync_modern_node" in publish
    assert "sync_installed_node_to_subscriptions" in publish
    assert "provision_account_v1" not in publish
    assert "modern_pairs_provisioned" in publish

    assert "pg_try_advisory_lock" in lockfix
    assert "pg_advisory_unlock" in lockfix
    assert ".with_for_update()" not in lockfix
    assert "subscription_row_lock=disabled" in lockfix

    print("modern_new_node_convergence_v1_smoke=ok")


if __name__ == "__main__":
    main()
