from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
from aiogram import Bot as AiogramBot

from .bot_text_middleware import BotTextRequestMiddleware
from . import telegram_runtime_bot as runtime


INSTALL_ENV_FILE = Path("/etc/twinpanel/install.env")
FRONTEND_ENV_FILE = Path("/etc/twinpanel/frontend.env")


def _env_file_value(path: Path, key: str) -> str:
    try:
        for raw in path.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines():
            line = raw.strip()
            if (
                not line
                or line.startswith("#")
                or "=" not in line
            ):
                continue

            current_key, value = line.split("=", 1)
            if current_key.strip() == key:
                return value.strip().strip('"').strip("'")
    except Exception:
        pass

    return ""


def _valid_port(value: str) -> str:
    raw = str(value or "").strip()
    if not raw.isdigit():
        return ""

    port = int(raw)
    if 1 <= port <= 65535:
        return str(port)

    return ""


def _resolve_internal_api_base() -> str:
    """Resolve the API endpoint actually installed on this controller.

    The Telegram service historically exported a fixed 8095 base even though
    TwinPanel supports TWINPANEL_API_PORT. Prefer an explicit bot override,
    then the live installed API port, then the frontend's canonical backend
    URL, and only then the legacy runtime value.
    """
    explicit = str(
        os.getenv("TWINPANEL_BOT_API_BASE", "")
    ).strip()
    if explicit:
        return explicit.rstrip("/")

    port = _valid_port(
        os.getenv("TWINPANEL_API_PORT", "")
    ) or _valid_port(
        _env_file_value(
            INSTALL_ENV_FILE,
            "TWINPANEL_API_PORT",
        )
    )
    if port:
        return f"http://127.0.0.1:{port}"

    backend_url = _env_file_value(
        FRONTEND_ENV_FILE,
        "TWINPANEL_BACKEND_URL",
    ).rstrip("/")
    if backend_url.startswith(
        ("http://127.0.0.1:", "http://localhost:")
    ):
        return backend_url

    return str(
        runtime.API_BASE
        or "http://127.0.0.1:8095"
    ).rstrip("/")


def _install_internal_api_resilience() -> None:
    runtime.API_BASE = _resolve_internal_api_base()
    original_request = runtime.request

    async def resilient_request(
        method,
        path,
        *,
        token=None,
        bot_auth=False,
        payload=None,
    ):
        # Keep retries bounded and limited strictly to transport failures.
        # 4xx/5xx responses still flow through the original runtime unchanged.
        delays = (0.25, 0.5, 1.0, 2.0, 3.0)

        for attempt in range(len(delays) + 1):
            try:
                return await original_request(
                    method,
                    path,
                    token=token,
                    bot_auth=bot_auth,
                    payload=payload,
                )
            except (
                httpx.NetworkError,
                httpx.TimeoutException,
                httpx.RemoteProtocolError,
            ) as exc:
                if attempt >= len(delays):
                    raise RuntimeError(
                        "ارتباط داخلی با Twin Panel موقتاً در دسترس نیست. "
                        "چند لحظه بعد دوباره تلاش کنید."
                    ) from exc

                await asyncio.sleep(delays[attempt])

    runtime.request = resilient_request


class TextAwareBot(AiogramBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session.middleware(
            BotTextRequestMiddleware(scope="admin")
        )


async def main() -> None:
    # Keep the existing runtime, routers, payment flow, FSM and notifications.
    # Only the Bot constructor and internal API transport resilience are added.
    runtime.Bot = TextAwareBot
    _install_internal_api_resilience()
    await runtime.main()


if __name__ == "__main__":
    asyncio.run(main())
