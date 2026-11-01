from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIDDLEWARE = ROOT / "backend/app/bot_text_middleware.py"
DELIVERY = ROOT / "backend/app/routers/reseller_bot_delivery_runtime_v2.py"
ROUTERS_INIT = ROOT / "backend/app/routers/__init__.py"


def _source(path: Path) -> str:
    value = path.read_text(encoding="utf-8")
    ast.parse(value, filename=str(path))
    return value


def main() -> None:
    middleware = _source(MIDDLEWARE)
    delivery = _source(DELIVERY)
    routers_init = _source(ROUTERS_INIT)

    phrase = "تعداد فروش محدود نیست؛ مصرف واقعی از حجم نماینده کم می‌شود."
    assert 'self.scope == "reseller"' in middleware
    assert phrase in middleware
    assert 'result = result.replace(' in middleware

    assert "async def send_order_delivery_to_telegram_v2" in delivery
    assert "await bot.send_message(" in delivery
    assert "await bot.session.close()" in delivery
    assert "legacy._send_order_delivery_to_telegram = send_order_delivery_to_telegram_v2" in delivery

    assert "reseller_bot_delivery_runtime_v2" in routers_init

    print("reseller bot account delivery smoke: ok")


if __name__ == "__main__":
    main()
