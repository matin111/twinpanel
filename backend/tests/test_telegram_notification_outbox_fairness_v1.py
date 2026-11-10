"""Regression: old undeliverable messages may not block paid purchases."""
from __future__ import annotations

import ast
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "app/telegram_runtime_bot.py"


def queue_order(rows: list[dict], *, limit: int = 20) -> list[int]:
    """Model the canonical SQL ORDER BY on pending notifications."""
    pending = [r for r in rows if r["delivered_at"] is None]
    return [
        r["id"] for r in sorted(pending, key=lambda r: (r["attempts"], r["id"]))
    ][:limit]


class TelegramNotificationStarvationTest(TestCase):
    def test_real_outbox_code_uses_fair_ordering_before_limit(self):
        src = BOT.read_text()
        ast.parse(src)
        start = src.index("async def _telegram_notification_worker(")
        end = src.index("\nasync def main()", start)
        worker = src[start:end]
        self.assertIn("TelegramNotification.attempts.asc()", worker)
        self.assertIn("TelegramNotification.id.asc()", worker)
        self.assertLess(
            worker.index("TelegramNotification.attempts.asc()"),
            worker.index(".limit(20)"),
        )
        self.assertIn("TelegramNotification.delivered_at", worker)
        self.assertIn("row.delivered_at =", worker)
        self.assertIn("row.attempts += 1", worker)

    def test_20_unreachable_old_recipients_do_not_starve_fulfilled_order(self):
        rows = [
            {"id": i, "attempts": 100_000, "kind": "user_notification",
             "delivered_at": None}
            for i in range(1, 21)
        ]
        rows.append({
            "id": 21, "attempts": 0, "kind": "payment_approved",
            "delivered_at": None,
        })
        selected = queue_order(rows)
        self.assertEqual(selected[0], 21)

    def test_newly_queued_purchase_remains_prioritized(self):
        rows = [
            {"id": i, "attempts": 1, "kind": "user_notification",
             "delivered_at": None}
            for i in range(1, 35)
        ]
        rows.append({"id": 35, "attempts": 0, "kind": "payment_approved",
                     "delivered_at": None})
        self.assertEqual(queue_order(rows)[0], 35)

    def test_delivered_messages_cannot_be_selected_twice(self):
        rows = [
            {"id": 1, "attempts": 0, "kind": "payment_approved",
             "delivered_at": "sent"},
            {"id": 2, "attempts": 1, "kind": "payment_approved",
             "delivered_at": None},
        ]
        self.assertEqual(queue_order(rows), [2])


if __name__ == "__main__":
    main()
