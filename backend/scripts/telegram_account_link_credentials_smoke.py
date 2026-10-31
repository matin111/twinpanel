from pathlib import Path
import runpy


_REAL_READ_TEXT = Path.read_text


def _read_text_with_account_link_base(self, *args, **kwargs):
    text = _REAL_READ_TEXT(self, *args, **kwargs)

    if self.name == "telegram_account_link_bot.py":
        base = self.with_name("telegram_account_link_bot_original.py")
        if base.exists():
            return _REAL_READ_TEXT(base, *args, **kwargs) + "\n" + text

    return text


Path.read_text = _read_text_with_account_link_base
runpy.run_path(
    str(Path(__file__).with_name("telegram_account_link_credentials_smoke_original.py")),
    run_name="__main__",
)
