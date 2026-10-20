from __future__ import annotations

import asyncio

from aiogram import Bot as AiogramBot

from .bot_text_middleware import BotTextRequestMiddleware
from . import telegram_runtime_bot as runtime


class TextAwareBot(AiogramBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session.middleware(
            BotTextRequestMiddleware(scope="admin")
        )


async def main() -> None:
    # Keep the existing runtime, routers, payment flow, FSM and notifications.
    # Only the Bot constructor is replaced so outgoing static copy can be
    # customized without changing transactional logic.
    runtime.Bot = TextAwareBot
    await runtime.main()


if __name__ == "__main__":
    asyncio.run(main())
