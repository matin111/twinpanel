from pathlib import Path

menu = Path('scripts/twinpanel-menu.sh')
text = menu.read_text(encoding='utf-8')

insert_anchor = '''backup_menu(){\n'''
install_func = r'''install_reinstall_menu(){
  header "Install / Reinstall TwinPanel"
  echo "  Installs the latest verified Stable release using TwinPanel's official installer."
  echo "  Existing database, backend environment, administrator and runtime settings are preserved."
  echo "  Services may restart while the installation is completed."
  echo

  if [[ ! -f "$ROOT/install.sh" ]]; then
    printf '%bOfficial installer is missing from the active release: %s/install.sh%b\n' \
      "$C_RED" "$ROOT" "$C_RESET"
    pause
    return
  fi

  if [[ -f "$BACKEND_ENV" ]]; then
    printf '%bExisting TwinPanel installation detected.%b\n' "$C_YELLOW" "$C_RESET"
  else
    printf '%bTwinPanel runtime configuration was not detected.%b\n' "$C_YELLOW" "$C_RESET"
  fi
  echo

  if ! confirm_action "Run the official TwinPanel installer now?"; then
    echo "  Cancelled."
    pause
    return
  fi

  echo
  printf '%bStarting official installer...%b\n' "$C_CYAN" "$C_RESET"
  if bash "$ROOT/install.sh"; then
    echo
    printf '%bTwinPanel installation / reinstall completed successfully.%b\n' "$C_GREEN" "$C_RESET"
  else
    rc=$?
    echo
    printf '%bInstaller exited with status %s. Existing data was not intentionally removed by this menu action.%b\n' \
      "$C_RED" "$rc" "$C_RESET"
  fi
  pause
}

'''

if 'install_reinstall_menu(){' not in text:
    if insert_anchor not in text:
        raise SystemExit('backup_menu anchor not found')
    text = text.replace(insert_anchor, install_func + insert_anchor, 1)

old_main = r'''    menu_item 1 "Panel status"
    menu_item 2 "Restart TwinPanel"
    menu_item 3 "Protocol management"
    menu_item 4 "Panel update"
    menu_item 5 "More tools"
    printf '\n'
    menu_item 0 "Exit"
'''
new_main = r'''    menu_item 1 "Panel status"
    menu_item 2 "Restart TwinPanel"
    menu_item 3 "Protocol management"
    menu_item 4 "Panel update"
    menu_item 5 "Install / Reinstall TwinPanel"
    menu_item 6 "More tools"
    printf '\n'
    menu_item 0 "Exit"
'''
if old_main not in text:
    raise SystemExit('main menu entries anchor not found')
text = text.replace(old_main, new_main, 1)

old_case = r'''      1) status_menu ;;
      2) restart_menu ;;
      3) protocol_menu ;;
      4) update_menu ;;
      5) more_menu ;;
      0) [[ -t 1 ]] && clear 2>/dev/null || true; exit 0 ;;
'''
new_case = r'''      1) status_menu ;;
      2) restart_menu ;;
      3) protocol_menu ;;
      4) update_menu ;;
      5) install_reinstall_menu ;;
      6) more_menu ;;
      0) [[ -t 1 ]] && clear 2>/dev/null || true; exit 0 ;;
'''
if old_case not in text:
    raise SystemExit('main menu case anchor not found')
text = text.replace(old_case, new_case, 1)
menu.write_text(text, encoding='utf-8')

smoke = Path('scripts/terminal_install_reinstall_menu_smoke.py')
smoke.write_text(r'''#!/usr/bin/env python3
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
''', encoding='utf-8')

Path('.github/tmp_patch_terminal_install_menu.py').unlink(missing_ok=True)
Path('.github/workflows/tmp-terminal-install-menu-patch.yml').unlink(missing_ok=True)
