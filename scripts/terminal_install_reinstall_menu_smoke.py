#!/usr/bin/env python3
from pathlib import Path

src = Path('scripts/twinpanel-menu.sh').read_text(encoding='utf-8')

assert 'install_reinstall_menu(){' in src
assert 'menu_item 5 "Install / Reinstall TwinPanel"' in src
assert 'menu_item 6 "More tools"' in src
assert '5) install_reinstall_menu ;;' in src
assert '6) more_menu ;;' in src
assert 'bash "$ROOT/install.sh"' in src
assert 'Existing database, backend environment, administrator and runtime settings are preserved.' in src
assert 'Run the official TwinPanel installer now?' in src
print('TERMINAL_INSTALL_REINSTALL_MENU_SMOKE=PASS')
