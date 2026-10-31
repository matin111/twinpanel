def install_main_bot_extensions():
    """Install small main-bot extensions before wallet router construction."""

    from . import telegram_wallet_bot
    from .telegram_account_link_bot import install_account_link_feature

    if getattr(
        telegram_wallet_bot,
        "_main_extensions_installed",
        False,
    ):
        return

    original_create_wallet_router = telegram_wallet_bot.create_wallet_router

    def create_wallet_router_with_extensions(
        request_fn,
        session_fn,
    ):
        router = original_create_wallet_router(
            request_fn,
            session_fn,
        )

        return install_account_link_feature(
            router,
            request_fn,
            session_fn,
        )

    telegram_wallet_bot.create_wallet_router = (
        create_wallet_router_with_extensions
    )
    telegram_wallet_bot._main_extensions_installed = True
