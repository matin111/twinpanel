"""Static safety contract for bounded convergence, import isolation and admin compatibility."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
convergence = (root / "app/node_subscription_convergence_v114.py").read_text()
classic = (root / "app/routers/account_delivery.py").read_text()
assert 'TWINPANEL_CONVERGENCE_WORKER_V2' in convergence
assert '_reconcile_bounded_exit_nodes_once()' in convergence
assert 'Path("/run/twinpanel-convergence-batch-v360.json")' in convergence
assert 'Subscription.status == SubscriptionStatus.ACTIVE' in convergence
assert 'MigrationImportRecord.subscription_id' in convergence
assert 'not had_errors' in convergence
assert 'subscription_ids: set[int] | None = None' in convergence
assert 'subscription_ids: set[int] | None = None' in classic
assert 'if subscription_ids is not None:' in classic
assert 'if subscription_ids is not None and int(sub_id) not in subscription_ids:' in convergence
assert 'if int(sub.id) in imported_ids:' in convergence
assert 'int(sub.id) not in imported_ids' in classic
print("bounded new-account convergence safety smoke passed")
