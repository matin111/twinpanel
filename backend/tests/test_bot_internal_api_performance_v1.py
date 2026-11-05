"""Fast, safe Telegram<->API read-path contract regressions.

Critical payment/sales paths remain uncached. Public plan serialization must
still return all protocol/node/type fields and preserve the legacy fallback.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_and_admin_plan_lists_use_batched_snapshots():
    s = source("backend/app/routers/plans.py")
    assert "def _batch_plan_snapshots(db: Session, plans: list[Plan])" in s
    assert s.count("snapshots = _batch_plan_snapshots(db, rows)") == 2
    assert s.count("_plan_payload(db, plan, snapshots[int(plan.id)])") == 2
    assert '"category": snapshot["category"]' in s
    assert '"subscription_type": snapshot["subscription_type"]' in s
    assert '"sort_order": snapshot["sort_order"]' in s
    assert '"protocols": snapshot["protocols"]' in s
    assert '"node_ids": snapshot["node_ids"]' in s


def test_bulk_plan_loader_keeps_per_plan_visibility_and_sorting():
    s = source("backend/app/routers/plans.py")
    tree = ast.parse(s)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and
              n.name == "_batch_plan_snapshots")
    body = ast.get_source_segment(s, fn)
    assert "Plan.is_active" in s
    assert "PlanCategoryAssignment.plan_id.in_(ids)" in body
    assert "PlanProtocol.plan_id.in_(ids)" in body
    assert "PlanNode.plan_id.in_(ids)" in body
    assert "Node.node_type == NodeType.EXIT" in body
    assert "Node.retired_at.is_(None)" in body
    assert "admin_can_use_mother(db)" in body
    assert "[key for key in ALL_PROTOCOL_KEYS if key in present]" in body
    assert "explicit_nodes[plan_id] or eligible_nodes" in body


def test_bot_uses_one_bounded_http_client_for_runtime_lifetime():
    s = source("backend/app/telegram_runtime_custom.py")
    assert "async with httpx.AsyncClient(" in s
    assert "max_connections=30" in s
    assert "max_keepalive_connections=15" in s
    assert "trust_env=False" in s
    assert "_install_internal_api_resilience(client)" in s
    assert "httpx.NetworkError" in s
    assert "httpx.TimeoutException" in s
    assert "httpx.RemoteProtocolError" in s
    assert 'headers["X-Telegram-Bot-Secret"] = runtime.BOT_SECRET' in s


def test_bot_menu_only_uses_short_cache_and_checkout_forces_fresh_read():
    s = source("backend/app/telegram_purchase_bot.py")
    assert "plans_lock = asyncio.Lock()" in s
    assert "time.monotonic() + 3.0" in s
    assert "async def load_plans(*, force_refresh=False):" in s
    assert "plans = await load_plans(force_refresh=True)" in s
    assert '"/v1/store/orders"' in s
    assert '"/v1/payments/intents"' in s
    assert '"/v1/plans"' in s
