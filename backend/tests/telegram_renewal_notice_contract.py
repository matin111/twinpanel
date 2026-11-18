"""Safety contract for lifecycle-triggered Telegram renewal receipts.

These assertions specifically catch the regression where a paid renewal was
stored but no Telegram outbox message was created.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"
producer = (ROOT / "reserved_renewal_service.py").read_text(encoding="utf-8")
bot = (ROOT / "telegram_runtime_bot.py").read_text(encoding="utf-8")
queue = (ROOT / "telegram_notify_service.py").read_text(encoding="utf-8")

def test_reserved_renewal_notified_transactionally():
    before_return = producer.split("    return item\n", 1)[0]
    assert 'event_key=f"renewal-reserved:{int(item.id)}"' in before_return
    assert 'kind="renewal_reserved"' in before_return
    assert 'user_id=int(sub.user_id)' in before_return
    assert "db.commit()" not in before_return.split("# Transactional outbox:")[-1]

def test_activation_notified_in_same_transaction():
    after_activation = producer.split('pending.status = "activated"', 1)[1]
    assert 'event_key=f"renewal-activated:{int(pending.id)}"' in after_activation
    assert 'kind="renewal_activated"' in after_activation
    assert after_activation.index('kind="renewal_activated"') < after_activation.index("db.commit()")

def test_worker_distinguishes_reserved_from_active():
    assert 'row.kind in {"renewal_reserved", "renewal_activated"}' in bot
    assert '"🕒 تمدید برای دوره بعد رزرو شده' in bot
    assert '"🟢 دوره جدید فعال است' in bot
    assert 'row.kind == "renewal_reserved"' in bot
    assert 'current_status == "activated"' in bot
    assert 'event_key=f"renewal-reserved:{int(item.id)}"' in producer
    assert 'existing = (' in queue

if __name__ == "__main__":
    test_reserved_renewal_notified_transactionally()
    test_activation_notified_in_same_transaction()
    test_worker_distinguishes_reserved_from_active()
    print("TELEGRAM_RENEWAL_NOTICE_CONTRACT_OK")
