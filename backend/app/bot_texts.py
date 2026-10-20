from __future__ import annotations

from .routers import telegram_manager


# TWINPANEL_BOT_TEXT_RUNTIME_V1
# The canonical settings storage/API lives in routers.general_settings and
# routers.reseller_bot. This module has one responsibility only: make the
# existing main-bot service manager launch the text-aware wrapper while keeping
# every existing install/start/stop/restart endpoint and systemd behavior.
if not getattr(
    telegram_manager,
    "_twinpanel_bot_text_runtime_v1",
    False,
):
    _original_service_text = telegram_manager._service_text

    def _service_text_with_bot_texts() -> str:
        return _original_service_text().replace(
            "-m app.telegram_runtime_bot",
            "-m app.telegram_runtime_custom",
        )

    telegram_manager._service_text = _service_text_with_bot_texts
    telegram_manager._twinpanel_bot_text_runtime_v1 = True
