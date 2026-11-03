from pathlib import Path

from app.telegram_button_styles import TelegramButtonStyles
from app.routers.telegram_membership_settings import TelegramButtonStylesIn


ROOT = Path(__file__).resolve().parents[2]


def test_trial_style_exists_in_backend_contracts():
    assert TelegramButtonStyles().trial == "primary"
    assert TelegramButtonStylesIn().trial == "primary"


def test_main_bot_trial_uses_live_saved_style():
    source = (ROOT / "app" / "telegram_account_link_bot.py").read_text(encoding="utf-8")
    assert '"🎁 اکانت تست"' in source
    assert "style=styles.trial" in source
    assert 'style="primary"' not in source.split('"🎁 اکانت تست"', 1)[1].split("],", 1)[0]


def test_admin_ui_manages_and_previews_trial_style():
    source = (ROOT.parent / "components" / "telegram-button-style-settings.tsx").read_text(encoding="utf-8")
    assert 'trial:Style' in source
    assert 'key:"trial",label:"اکانت تست"' in source
    assert 'cls(styles.trial)' in source
    assert "همان ۱۱ دکمه /start" in source
