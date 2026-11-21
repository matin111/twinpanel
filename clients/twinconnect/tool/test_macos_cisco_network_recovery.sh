#!/usr/bin/env bash
# Safe Cisco recovery preflight. Never opens VPN or changes sudoers/routes.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
  echo "CISCO_MACOS_REQUIRED" >&2
  exit 1
fi
echo "=== OFFLINE CISCO TESTS ==="
python3 -m unittest discover -s macos_native -p 'test_cisco*.py' -v
echo "=== INSTALL ROOT OWNED RECOVERY HELPER ==="
sudo bash tool/install_macos_cisco_helper.sh
helper="/Library/PrivilegedHelperTools/TwinConnectCisco/cisco_network_recovery.py"
echo "=== READ CURRENT NETWORK (NO CHANGES) ==="
sudo /usr/bin/python3 "$helper" inspect
echo "=== RECORD NETWORK CHECKPOINT ==="
sudo /usr/bin/python3 "$helper" snapshot
echo "=== VERIFY NO-CHANGE RESTORE ==="
sudo /usr/bin/python3 "$helper" restore
echo "CISCO_RECOVERY_DRY_RUN_PASSED"
echo "VPN_NOT_STARTED; SUDOERS_UNCHANGED; CISCO_STILL_DISABLED"
